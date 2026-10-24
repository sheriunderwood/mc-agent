// wearing: the agent's "what are they wearing" HUD.
//
// The avatar wears this as a HUD. It reads people's attachments (name,
// description, creator, attach point) and tells the avatar privately (llOwnerSay).
// The agent's program, not the AI, saves that: friends/<name>/wearing-YY-MM-DD-HH-mm.md
// for people it knows, wearing/<avatar name>-YY-MM-DD-HH-mm.md for anyone else.
//
// To keep it light, it only scans people within normal chat range (20 m):
// - At home (the home parcel and region in config.toml) it scans automatically: each
//   person who comes within 20 m, 30 s later so their outfit has rezzed, and
//   not again within an hour (someone near the 20 m line drifts in and out).
//   The avatar's own outfit, once, a minute after it's attached (after a login
//   an outfit takes a while to rez).
// - Anywhere else it only scans when asked: "scan <name or uuid>".
//
// Scripts can see what people have attached, the same as the "What is she
// wearing?" HUDs on the Marketplace, but not their HUDs, and not system
// clothing or body parts (BOM layers).
//
// Messages to the avatar, one every 10 s: MC holds back an object's lines past
// 10 a minute (counting these answers too), and a held line never reaches the
// agent. If a part goes missing anyway, the agent asks for it again with
// "resend"; the HUD keeps its last few dozen messages for that. One scan is sent as N
// parts, each a batch of attachments; part 1 also carries who and where:
//   wearing:{"t":"part","a":<avatar>,"k":1,"of":<N>,"n":<name>,"d":<display name>,"c":<count>,
//            "r":<region>,"p":<parcel>,"v":<version>,"m":<auto|asked>,"i":[[<point>,<name>,<creator>,<description>],...]}
//   wearing:{"t":"part","a":<avatar>,"k":<2..N>,"of":<N>,"i":[...]}
// (v1.0 sent begin / items / end messages; the agent still reads those.)
// The JSON is built by hand: see str().
//
// Commands on its channel, from the avatar or an owner:
//
// Values in @@...@@ are filled in by the agent's install_script from config.toml
// and OWNERS.md: install it that way rather than pasting this file.
//   status                 version, where, auto scanning or not, scans waiting
//   scan <uuid or name>    one person within 20 m, now (anywhere)
//   scan                   everyone within 20 m, now (at home only)
//   auto on | auto off     automatic scanning at home (on by default)
//   resend <uuid> <k,k...> send those parts of the last scan of them again (the agent asks)
//   debug [on | off]       two lines per round of scanning, to whoever switched it on
//                          (an owner): when it starts, and when it's all sent (who, and how
//                          many messages). Not to the avatar, so they don't count against
//                          its chat's flood limit. Plain "debug" switches it on or off.
// Answers come back as "wearing_hud: ...".

string VERSION = "1.4.0";   // semantic version: see scripts/README.md
integer CMD_CHANNEL = @@WEARING_CHANNEL@@;
list OWNERS = [@@OWNERS@@];         // the avatar's owners' UUIDs (OWNERS.md), as strings
string HOME_REGION = "@@HOME_REGION@@";
string HOME_PARCEL = "@@HOME_PARCEL@@";
float RANGE = 20.0;         // normal chat range: nobody further away is scanned
float TICK = 10.0;          // seconds between messages (MC's flood limit is 10 a minute), and queue checks
float POLL = 15.0;          // how often to look for people coming within range (at home)
float SETTLE = 30.0;        // wait this long after someone comes close, so their outfit has rezzed
float SELF_SETTLE = 60.0;   // the avatar's own scan, after attaching: after a login an outfit takes a while
float RESCAN_AFTER = 3600.0;   // no automatic rescan of the same person within an hour
integer MAX_BYTES = 700;    // bytes of attachments per message: chat stops at 1024 bytes, and the
                            // part-1 header (names, region, parcel) can take ~250 more
integer KEEP = 30;          // messages kept for resending

list gNear;         // who was within range at the last look
list gQueue;        // strided [when to scan (llGetTime), avatar, "auto" or "asked"]
list gOut;          // messages waiting to be sent
list gSent;         // strided [avatar, part, message]: the last KEEP sent, for resend
list gScanned;      // strided [avatar, when (llGetTime)]: recent scans, for RESCAN_AFTER
integer gAuto = TRUE;
key gDebugTo;       // who hears the debug lines (NULL_KEY: debug off)
integer gBusy;      // a round of scanning is under way
list gRound;        // who this round scanned, for the "done" line
integer gRoundSent; // messages sent this round
float gLastPoll;

hud(string msg)
{
    llOwnerSay("wearing_hud: " + msg);
}

vector myPos()
{
    return llList2Vector(llGetObjectDetails(llGetOwner(), [OBJECT_POS]), 0);
}

integer atHome()
{
    return llGetRegionName() == HOME_REGION
        && llList2String(llGetParcelDetails(myPos(), [PARCEL_DETAILS_NAME]), 0) == HOME_PARCEL;
}

// Within normal chat range of the avatar, and in the region.
integer inRange(key av)
{
    if (llGetAgentSize(av) == ZERO_VECTOR) return FALSE;
    return llVecDist(llList2Vector(llGetObjectDetails(av, [OBJECT_POS]), 0), myPos()) <= RANGE;
}

// Everyone within range now (not the avatar).
list near()
{
    list out;
    list all = llGetAgentList(AGENT_LIST_REGION, []);
    integer i;
    for (i = 0; i < llGetListLength(all); ++i)
    {
        key av = llList2Key(all, i);
        if (av != llGetOwner() && inRange(av)) out += av;
    }
    return out;
}

queue(key av, float delay, string why)
{
    if (llListFindList(gQueue, [av]) != -1) return;   // already waiting
    if (why == "auto")
    {
        integer at = llListFindList(gScanned, [av]);
        if (at != -1 && llGetTime() - llList2Float(gScanned, at + 1) < RESCAN_AFTER) return;   // scanned lately
    }
    gQueue += [llGetTime() + delay, av, why];
}

// Read someone's attachments and line up the messages about them.
scan(key av, string why)
{
    if (av != llGetOwner() && !inRange(av)) return;   // walked off, or left
    list att = llGetAttachedList(av);
    if (llGetListLength(att) == 1 && llStringLength(llList2String(att, 0)) != 36) return;   // "NOT FOUND" and the like
    integer n = llGetListLength(att);
    integer seen = llListFindList(gScanned, [av]);
    if (seen != -1) gScanned = llDeleteSubList(gScanned, seen, seen + 1);
    gScanned += [av, llGetTime()];
    if (llGetListLength(gScanned) > 200) gScanned = llDeleteSubList(gScanned, 0, 1);
    // Batches of attachments, each one message's worth (as JSON arrays, joined).
    list batches;
    string cur = "";
    integer i;
    for (i = 0; i < n; ++i)
    {
        list d = llGetObjectDetails(llList2Key(att, i),
                                    [OBJECT_ATTACHED_POINT, OBJECT_NAME, OBJECT_CREATOR, OBJECT_DESC]);
        string item = "[" + (string)llList2Integer(d, 0) + "," + str(llList2String(d, 1)) + ","
                      + str(llList2String(d, 2)) + "," + str(llList2String(d, 3)) + "]";
        if (cur != "" && bytes(cur + "," + item) > MAX_BYTES) { batches += cur; cur = ""; }
        if (cur == "") cur = item;
        else cur += "," + item;
    }
    batches += cur;      // the last batch (empty if nothing's attached: still one part)
    integer of = llGetListLength(batches);
    if (!gBusy) debug("started scanning (" + why + ")");
    gBusy = TRUE;
    gRound += llKey2Name(av) + " (" + (string)n + ")";
    for (i = 0; i < of; ++i)
    {
        string head = "\"t\":\"part\",\"a\":" + str((string)av) + ",\"k\":" + (string)(i + 1)
                      + ",\"of\":" + (string)of;
        if (i == 0)
            head += ",\"n\":" + str(llKey2Name(av)) + ",\"d\":" + str(llGetDisplayName(av))
                  + ",\"c\":" + (string)n + ",\"r\":" + str(llGetRegionName())
                  + ",\"p\":" + str(llList2String(llGetParcelDetails(myPos(), [PARCEL_DETAILS_NAME]), 0))
                  + ",\"v\":" + str(VERSION) + ",\"m\":" + str(why);
        string m = "wearing:{" + head + ",\"i\":[" + llList2String(batches, i) + "]}";
        gOut += m;
        // Kept for resend (an earlier scan of the same person is replaced).
        integer old = llListFindList(gSent, [(string)av, i + 1]);
        if (old != -1) gSent = llDeleteSubList(gSent, old, old + 2);
        gSent += [(string)av, i + 1, m];
        if (llGetListLength(gSent) > KEEP * 3) gSent = llDeleteSubList(gSent, 0, 2);
    }
}

// At home: who has come within range since the last look. Queue them, after SETTLE.
poll()
{
    gLastPoll = llGetTime();
    if (!gAuto || !atHome()) { gNear = []; return; }
    list now = near();
    integer i;
    for (i = 0; i < llGetListLength(now); ++i)
        if (llListFindList(gNear, [llList2Key(now, i)]) == -1) queue(llList2Key(now, i), SETTLE, "auto");
    gNear = now;
}

start()
{
    gQueue = [];
    gOut = [];
    gNear = [];
    llListen(CMD_CHANNEL, "", NULL_KEY, "");
    if (gAuto && atHome()) queue(llGetOwner(), SELF_SETTLE, "auto");   // the avatar's own outfit, once it's rezzed
    gLastPoll = llGetTime() - POLL + 5.0;                      // first look in 5 s
    llSetTimerEvent(TICK);
}

// A JSON string, built by hand. (llList2Json treats text that looks like JSON,
// e.g. an item named "[shop] Hair" or a description like "{...}", as JSON, and
// one bad one spoils the whole message.)
string str(string text)
{
    text = llDumpList2String(llParseStringKeepNulls(text, ["\\"], []), "\\\\");
    text = llDumpList2String(llParseStringKeepNulls(text, ["\""], []), "\\\"");
    text = llDumpList2String(llParseStringKeepNulls(text, ["\n"], []), "\\n");
    text = llDumpList2String(llParseStringKeepNulls(text, ["\t"], []), "\\t");
    return "\"" + text + "\"";
}

// A string's size in UTF-8 bytes (chat's limit is in bytes; fancy Unicode
// letters in item names take 2-4 bytes each). LSL has no byte count, but
// base64 makes 4 characters of every 3 bytes.
integer bytes(string text)
{
    string b64 = llStringToBase64(text);
    integer pad = (llGetSubString(b64, -1, -1) == "=") + (llGetSubString(b64, -2, -2) == "=");
    return llStringLength(b64) / 4 * 3 - pad;
}

debug(string msg)
{
    if (gDebugTo != NULL_KEY && llGetAgentSize(gDebugTo) != ZERO_VECTOR)
        llRegionSayTo(gDebugTo, PUBLIC_CHANNEL, "wearing_hud debug: " + msg);
}

string where()
{
    if (atHome()) return "at home (" + HOME_PARCEL + ")";
    return "away (" + llGetRegionName() + ")";
}

default
{
    state_entry()
    {
        if (llGetAttached()) start();
    }

    attach(key id)
    {
        if (id != NULL_KEY) start();
        else llSetTimerEvent(0.0);
    }

    changed(integer change)
    {
        if (change & CHANGED_OWNER) llResetScript();
        if (change & (CHANGED_REGION | CHANGED_TELEPORT))
        {
            gQueue = [];      // somewhere new: anything waiting is stale
            gNear = [];       // and at home, everyone close counts as arriving
        }
    }

    listen(integer channel, string speaker, key id, string message)
    {
        if (id != llGetOwner() && llListFindList(OWNERS, [(string)id]) == -1) return;
        string msg = llStringTrim(message, STRING_TRIM);
        string word = llToLower(llList2String(llParseString2List(msg, [" "], []), 0));
        string rest = llStringTrim(llGetSubString(msg + " ", llStringLength(word), -1), STRING_TRIM);
        if (word == "status")
        {
            string a = "off";
            if (gAuto) a = "on";
            hud("v" + VERSION + ", " + where() + ", auto " + a + " (home only), "
                + (string)llGetListLength(near()) + " people within " + (string)((integer)RANGE) + " m, "
                + (string)(llGetListLength(gQueue) / 3) + " scans and " + (string)llGetListLength(gOut)
                + " messages waiting");
        }
        else if (word == "scan" && rest == "")
        {
            if (!atHome()) { hud("away from home I only scan one person: scan <name or uuid>"); return; }
            list now = near();
            integer i;
            for (i = 0; i < llGetListLength(now); ++i) queue(llList2Key(now, i), 0.0, "asked");
            hud("scanning everyone within " + (string)((integer)RANGE) + " m (" + (string)llGetListLength(now) + ")");
        }
        else if (word == "scan")
        {
            key av = (key)rest;
            if (llStringLength(rest) != 36) av = llName2Key(rest);
            if (av == NULL_KEY || llGetAgentSize(av) == ZERO_VECTOR) { hud("\"" + rest + "\" isn't in this region"); return; }
            if (av != llGetOwner() && !inRange(av))
            {
                hud(llKey2Name(av) + " is more than " + (string)((integer)RANGE) + " m away: get closer first");
                return;
            }
            queue(av, 0.0, "asked");
            hud("scanning " + llKey2Name(av));
        }
        else if (word == "resend")
        {
            // "resend <uuid> 3" or "resend <uuid> 2,4": back to the front of the queue.
            list p = llParseString2List(rest, [" "], []);
            string av = llToLower(llList2String(p, 0));
            list parts = llParseString2List(llList2String(p, 1), [","], []);
            list again;
            integer i;
            for (i = 0; i < llGetListLength(parts); ++i)
            {
                integer at = llListFindList(gSent, [av, (integer)llList2String(parts, i)]);
                if (at != -1) again += llList2String(gSent, at + 2);
            }
            gOut = again + gOut;
            if (again == []) hud("nothing to resend for " + av);
            else gBusy = TRUE;
        }
        else if (word == "debug")
        {
            rest = llToLower(rest);
            if (rest == "on" || (rest == "" && gDebugTo == NULL_KEY)) gDebugTo = id;
            else gDebugTo = NULL_KEY;
            if (gDebugTo != NULL_KEY) debug("debug on (v" + VERSION + ", " + where() + ")");
            else llRegionSayTo(id, PUBLIC_CHANNEL, "wearing_hud debug: off");
        }
        else if (word == "auto")
        {
            gAuto = llToLower(rest) != "off";
            string a = "off";
            if (gAuto) a = "on";
            hud("auto " + a + " (it only scans automatically at home)");
        }
        else hud("unknown command \"" + word + "\"");
    }

    timer()
    {
        // One message per tick, so the chat flood limits don't hold them back.
        if (gOut != [])
        {
            llOwnerSay(llList2String(gOut, 0));
            gOut = llDeleteSubList(gOut, 0, 0);
            ++gRoundSent;
            return;
        }
        if (gBusy && gQueue == [])
        {
            string who = llDumpList2String(gRound, ", ");
            if (who == "") who = "nobody new (resends only)";
            debug("done: " + who + "; " + (string)gRoundSent + " messages sent");
            gBusy = FALSE;
            gRound = [];
            gRoundSent = 0;
        }
        if (llGetTime() - gLastPoll >= POLL) poll();
        // The next scan that's due.
        integer i;
        for (i = 0; i < llGetListLength(gQueue); i += 3)
        {
            if (llList2Float(gQueue, i) <= llGetTime())
            {
                key av = llList2Key(gQueue, i + 1);
                string why = llList2String(gQueue, i + 2);
                gQueue = llDeleteSubList(gQueue, i, i + 2);
                scan(av, why);
                return;
            }
        }
    }
}
