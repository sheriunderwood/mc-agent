// dance_hud: the agent's smart dance HUD (the main script).
//
// Put it in a prim near where the avatar stands, together with copies of
// dance_slot (one per dancer) and the dances (animations). The avatar sends it
// commands on its channel; it answers the avatar privately, in local chat, as
// "dance_hud: ...". The agent reads those answers.
//
// Values in @@...@@ (the avatar, owners, channel) are filled in by the agent's
// install_script from config.toml and OWNERS.md: install it that way rather
// than pasting this file.
//
// Dances: every animation in the prim's contents (a prim's inventory has no
// folders). With none, the built-in dance1 to dance8 are used.
//
// Playlists: notecards in the prim named "<something>.lst" (calm_dances.lst,
// high_energy.lst), one dance name per line; blank lines and lines starting
// with # are skipped. "use calm_dances" makes play/sequence/random work from
// that list; "use all" goes back to every dance (the default). Names that
// aren't in the prim are reported and skipped.
//
// Dancers: each one needs a dance_slot script of their own, since a script can
// animate only one avatar. Drop in as many copies as dancers you want at once;
// SL numbers the copies ("dance_slot-v1.0.0 1", "... 2"...), and this script
// counts them. The avatar dancing too takes a slot.
//
// SAFETY: commands come only from the avatar, its owners (OWNERS.md), whoever
// owns the prim, and any extra commanders in config.toml ([huds]). Anyone dancing may say "leave" to stop,
// or type /99stop, the usual way to get off a dance HUD in SL.
// Everyone else is ignored. Nobody is animated without agreeing (the permission box, or
// having accepted the slot scripts' experience).
//
// An owner can type the same commands, e.g. /<channel>who or /<channel>remove Pixel.
// Answers go to whoever asked; joins and leaves go to the avatar, and to the
// owner too if they gave the last command.
//
// Someone who leaves the region (or stops the animation) is dropped within
// about 10 seconds, freeing their slot.
//
// Commands (the avatar says e.g. "invite <uuid>" on its channel):
//   status                          ready, slots, dancers, what's playing
//   list                            the dances in use (the playlist, or all), numbered
//   list all                        every dance in the prim, numbered
//   lists                           the playlists (*.lst notecards)
//   show <list>                     the dances in a playlist
//   use <list> | use all            dance from that playlist, or from everything
//   who                             who's dancing, and invites waiting
//   invite <uuid or name>           ask someone in the region to dance
//   remove <uuid, name or slot>     stop someone's dance and free their slot
//                                   (a name matches part of a dancer's name)
//   me on | me off                  the avatar dances too, or stands still
//   play <number or name>           everyone dances this, until told otherwise
//                                   (a number from list; any dance by name)
//   sequence [seconds]              every dance in order, changing every N s
//   random [seconds]                random dances, changing every N s
//   next                            the next dance now (sequence or random)
//   stop                            everyone stands still (they stay in)
//   debug [on | off]                owner only: say each dance as it starts, in
//                                   llOwnerSay ("now: <dance> (<playlist>, 3 of 12)"),
//                                   and each invite, join and drop; plain "debug"
//                                   switches it on or off
// From anyone dancing:
//   leave                           stop dancing and free the slot
//   /99stop (or /99leave)           the same, on channel 99 as other dance HUDs use;
//                                   nothing else is taken on channel 99, and a
//                                   commander's /99stop takes only them out

string VERSION = "1.4.0";   // semantic version: see scripts/README.md
integer CMD_CHANNEL = @@DANCE_CHANNEL@@;
integer STOP_CHANNEL = 99;   // SL habit: /99stop gets you off a dance HUD
key AVATAR = "@@AVATAR@@";          // the avatar the agent drives
list OWNERS = [@@OWNERS@@];         // its owners' UUIDs (OWNERS.md), as strings
list COMMANDERS = [@@COMMANDERS@@]; // anyone else allowed to give commands ([huds] extra_commanders)
float DEFAULT_SECONDS = 90.0;
float MIN_SECONDS = 15.0;

// Link messages between this script and the dance_slot scripts.
integer ALL_PLAY = 1;         // str: the dance
integer ALL_STOP = 2;
integer ALL_RELEASE = 5;      // everyone out: this script started over
integer SLOT_INVITE = 1000;   // + slot; id: the avatar
integer FROM_SLOT = 2000;     // + slot; str: joined | declined | timeout | left | removed
integer SLOT_RELEASE = 3000;  // + slot
integer SLOT_PLAY = 4000;     // + slot; str: the dance

list gDancers;        // strided [slot, avatar]
list gPending;        // strided [slot, avatar]: invites waiting for an answer
string gDance = "";
string gMode = "still";   // still | play | sequence | random
integer gIndex = -1;
float gSeconds = 90.0;
key gCommander = AVATAR;   // who hears the answers
integer gDebug;               // owner asked to hear each dance as it starts
list gPlaylist;               // the playlist's dances in use ([] with gListName "": all)
string gListName = "";        // the playlist notecard in use, or "" for all dances

// Reading a playlist notecard (one line at a time, through dataserver).
string gCard;
integer gLine;
key gQuery;
string gPurpose;              // show | use | reload
list gRead;

tell(string msg)
{
    llRegionSayTo(gCommander, PUBLIC_CHANNEL, "dance_hud: " + msg);
}

// Joins and leaves: the avatar always hears them (the agent keeps track),
// and whoever gave the last command if that's someone else (an owner).
notify(string msg)
{
    llRegionSayTo(AVATAR, PUBLIC_CHANNEL, "dance_hud: " + msg);
    if (gCommander != AVATAR) tell(msg);
}

integer owner(key id)
{
    return id == llGetOwner() || llListFindList(OWNERS, [(string)id]) != -1;
}

integer commander(key id)
{
    return id == AVATAR || owner(id) || llListFindList(COMMANDERS, [(string)id]) != -1;
}

list allDances()
{
    list out;
    integer n = llGetInventoryNumber(INVENTORY_ANIMATION);
    integer i;
    for (i = 0; i < n; ++i) out += llGetInventoryName(INVENTORY_ANIMATION, i);
    if (out == []) out = ["dance1", "dance2", "dance3", "dance4", "dance5", "dance6", "dance7", "dance8"];
    return out;
}

// The dances in use: the playlist's, or all of them.
list dances()
{
    if (gListName != "") return gPlaylist;
    return allDances();
}

// A dance in the prim by name, ignoring case; "" if there's none.
string findDance(string want)
{
    list all = allDances();
    integer i;
    want = llToLower(llStringTrim(want, STRING_TRIM));
    for (i = 0; i < llGetListLength(all); ++i)
        if (llToLower(llList2String(all, i)) == want) return llList2String(all, i);
    return "";
}

list playlists()
{
    list out;
    integer n = llGetInventoryNumber(INVENTORY_NOTECARD);
    integer i;
    for (i = 0; i < n; ++i)
    {
        string c = llGetInventoryName(INVENTORY_NOTECARD, i);
        if (llToLower(llGetSubString(c, -4, -1)) == ".lst") out += c;
    }
    return out;
}

// A playlist notecard by name, with or without ".lst", ignoring case; "" if none.
string findList(string want)
{
    list all = playlists();
    integer i;
    want = llToLower(llStringTrim(want, STRING_TRIM));
    if (llGetSubString(want, -4, -1) != ".lst") want += ".lst";
    for (i = 0; i < llGetListLength(all); ++i)
        if (llToLower(llList2String(all, i)) == want) return llList2String(all, i);
    return "";
}

readList(string card, string purpose)
{
    gCard = card;
    gLine = 0;
    gRead = [];
    gPurpose = purpose;
    gQuery = llGetNotecardLine(card, 0);
}

// A playlist has been read: the dances in it that the prim has, and the rest.
listRead()
{
    list ok;
    list missing;
    integer i;
    for (i = 0; i < llGetListLength(gRead); ++i)
    {
        string d = findDance(llList2String(gRead, i));
        if (d == "") missing += llList2String(gRead, i);
        else ok += d;
    }
    string note = "";
    if (missing != []) note = " (not in the prim, skipped: " + llDumpList2String(missing, ", ") + ")";
    if (gPurpose == "show")
    {
        sendItems(gCard + " (" + (string)llGetListLength(ok) + ")", ok);
        if (note != "") tell(gCard + note);
        return;
    }
    if (ok == [])
    {
        tell("none of the dances in " + gCard + " are in the prim" + note + "; still using " + listLabel());
        return;
    }
    gPlaylist = ok;
    gListName = gCard;
    gIndex = -1;
    if (gPurpose == "use") tell("using " + gCard + ": " + (string)llGetListLength(ok) + " dances" + note);
    if (gDebug) llOwnerSay("dance_hud debug: playlist " + gCard + " (" + (string)llGetListLength(ok) + " dances)" + note);
}

string listLabel()
{
    if (gListName == "") return "all dances";
    return gListName;
}

// The slot number at the end of a dance_slot script's name: "dance_slot-v1.0.0 3"
// (or "dance_slot 3") is 3; the first copy, with no number, is 0.
integer slotNumber(string script)
{
    list parts = llParseString2List(script, [" "], []);
    string last = llList2String(parts, -1);
    if (llGetListLength(parts) > 1 && (string)((integer)last) == last) return (integer)last;
    return 0;
}

// The slot numbers of the dance_slot scripts in the prim: "dance_slot" is 0,
// "dance_slot 3" is 3.
list slots()
{
    list out;
    integer n = llGetInventoryNumber(INVENTORY_SCRIPT);
    integer i;
    for (i = 0; i < n; ++i)
    {
        string s = llGetInventoryName(INVENTORY_SCRIPT, i);
        if (llSubStringIndex(s, "dance_slot") == 0)
            out += slotNumber(s);
    }
    return out;
}

integer freeSlot()
{
    list all = slots();
    integer i;
    for (i = 0; i < llGetListLength(all); ++i)
    {
        integer s = llList2Integer(all, i);
        if (llListFindList(llList2ListStrided(gDancers, 0, -1, 2), [s]) == -1
            && llListFindList(llList2ListStrided(gPending, 0, -1, 2), [s]) == -1)
            return s;
    }
    return -1;
}

// A UUID, or the name of someone in the region.
key person(string who)
{
    who = llStringTrim(who, STRING_TRIM);
    key k = (key)who;
    if (k == NULL_KEY || llStringLength(who) != 36) k = llName2Key(who);
    if (k == NULL_KEY || llGetAgentSize(k) == ZERO_VECTOR) return NULL_KEY;   // not in this region
    return k;
}

string name(key k)
{
    string n = llGetDisplayName(k);
    if (n == "") n = llKey2Name(k);
    if (n == "") n = (string)k;
    return n;
}

// Where someone is: the slot they dance in or wait for, or -1.
integer slotOf(list strided, key k)
{
    integer i = llListFindList(strided, [k]);
    if (i == -1) return -1;
    return llList2Integer(strided, i - 1);
}

// A dancer (or someone invited) by UUID, slot number, or part of their name.
key findDancer(string what)
{
    what = llStringTrim(what, STRING_TRIM);
    list all = gDancers + gPending;
    integer i;
    if (llStringLength(what) == 36 && llListFindList(all, [(key)what]) != -1) return (key)what;
    if ((string)((integer)what) == what && llListFindList(all, [(integer)what]) != -1)
        return llList2Key(all, llListFindList(all, [(integer)what]) + 1);
    string low = llToLower(what);
    for (i = 1; i < llGetListLength(all) && low != ""; i += 2)
    {
        key k = llList2Key(all, i);
        if (llSubStringIndex(llToLower(llGetDisplayName(k) + " " + llKey2Name(k)), low) != -1) return k;
    }
    return NULL_KEY;
}

drop(key k)
{
    integer i = llListFindList(gDancers, [k]);
    if (i != -1) gDancers = llDeleteSubList(gDancers, i - 1, i);
    i = llListFindList(gPending, [k]);
    if (i != -1) gPending = llDeleteSubList(gPending, i - 1, i);
}

invite(key k)
{
    if (k == NULL_KEY) { tell("they aren't in this region"); return; }
    if (slotOf(gDancers, k) != -1) { tell(name(k) + " is already dancing"); return; }
    if (slotOf(gPending, k) != -1) { tell("already waiting for " + name(k) + " to answer"); return; }
    integer s = freeSlot();
    if (s == -1) { tell("no free slot: add another copy of dance_slot to the prim"); return; }
    gPending += [s, k];
    llMessageLinked(LINK_THIS, SLOT_INVITE + s, "", k);
    tell("asking " + name(k) + " to dance (slot " + (string)s + ")");
    debugSay("invited " + name(k) + " (slot " + (string)s + ", by " + name(gCommander) + ")");
}

removePerson(key k)
{
    integer s = slotOf(gDancers, k);
    if (s == -1) s = slotOf(gPending, k);
    if (s == -1) { tell(name(k) + " isn't dancing"); return; }
    llMessageLinked(LINK_THIS, SLOT_RELEASE + s, "", k);
}

play(string dance)
{
    gDance = dance;
    llMessageLinked(LINK_THIS, ALL_PLAY, gDance, NULL_KEY);
    if (gDebug) sayNow();
}

// Debug: to the owner only (they must be in the region).
debugSay(string msg)
{
    if (gDebug) llOwnerSay("dance_hud debug: " + msg);
}

// Debug: what's playing.
sayNow()
{
    if (gMode == "still" || gDance == "") { llOwnerSay("dance_hud debug: nothing playing (" + listLabel() + ")"); return; }
    string where = listLabel();
    integer i = llListFindList(dances(), [gDance]);
    if (i != -1) where += ", " + (string)(i + 1) + " of " + (string)llGetListLength(dances());
    else where += ", not in this list";
    llOwnerSay("dance_hud debug: now " + gDance + " (" + where + ", " + gMode + ")");
}

next()
{
    list d = dances();
    integer n = llGetListLength(d);
    if (gMode == "random")
    {
        integer j = (integer)llFrand(n);
        if (n > 1 && llList2String(d, j) == gDance) j = (j + 1) % n;
        gIndex = j;
    }
    else gIndex = (gIndex + 1) % n;
    play(llList2String(d, gIndex));
}

string who()
{
    list names;
    integer i;
    for (i = 1; i < llGetListLength(gDancers); i += 2)
    {
        key k = llList2Key(gDancers, i);
        names += name(k) + " (slot " + llList2String(gDancers, i - 1) + ", " + (string)k + ")";
    }
    string out = "dancing (" + (string)(llGetListLength(gDancers) / 2) + "): " + llDumpList2String(names, ", ");
    if (names == []) out = "nobody dancing";
    if (gPending != [])
    {
        names = [];
        for (i = 1; i < llGetListLength(gPending); i += 2) names += name(llList2Key(gPending, i));
        out += "; waiting for: " + llDumpList2String(names, ", ");
    }
    return out;
}

// A numbered list, "header: 1. A | 2. B | ...", split into messages that fit.
sendItems(string header, list items)
{
    string line = header + ":";
    string sep = " ";
    integer i;
    for (i = 0; i < llGetListLength(items); ++i)
    {
        string item = sep + (string)(i + 1) + ". " + llList2String(items, i);
        if (llStringLength(line + item) > 900) { tell(line); line = "(more)"; item = " | " + llGetSubString(item, llStringLength(sep), -1); }
        line += item;
        sep = " | ";
    }
    tell(line);
}

default
{
    state_entry()
    {
        llMessageLinked(LINK_THIS, ALL_RELEASE, "", NULL_KEY);   // no dancers left over from before
        llListen(CMD_CHANNEL, "", NULL_KEY, "");
        llListen(STOP_CHANNEL, "", NULL_KEY, "");
    }

    on_rez(integer start_param) { llResetScript(); }

    changed(integer change)
    {
        if (change & (CHANGED_OWNER | CHANGED_REGION_START)) llResetScript();
        if ((change & CHANGED_INVENTORY) && gListName != "")
        {
            // The prim's contents changed: pick up a changed playlist, or fall back to all.
            if (llGetInventoryType(gListName) == INVENTORY_NOTECARD) readList(gListName, "reload");
            else
            {
                notify(gListName + " is gone from the prim; using all dances");
                gListName = "";
                gPlaylist = [];
            }
        }
    }

    dataserver(key query, string data)
    {
        if (query != gQuery) return;
        if (data == EOF) { listRead(); return; }
        data = llStringTrim(data, STRING_TRIM);
        if (data != "" && llGetSubString(data, 0, 0) != "#") gRead += data;
        gQuery = llGetNotecardLine(gCard, ++gLine);
    }

    listen(integer channel, string speaker, key id, string message)
    {
        string msg = llStringTrim(message, STRING_TRIM);
        string word = llToLower(llList2String(llParseString2List(msg, [" "], []), 0));
        string rest = llStringTrim(llGetSubString(msg + " ", llStringLength(word), -1), STRING_TRIM);

        // Channel 99 (/99stop): the speaker leaves, if they're dancing or invited.
        // Nothing else, even from a commander ("stop" on CMD_CHANNEL stops everyone).
        if (channel == STOP_CHANNEL)
        {
            if ((word == "stop" || word == "leave") && (slotOf(gDancers, id) != -1 || slotOf(gPending, id) != -1))
                removePerson(id);
            return;
        }

        // Anyone dancing may leave, commanders included.
        if (word == "leave" && (slotOf(gDancers, id) != -1 || slotOf(gPending, id) != -1))
        {
            if (commander(id)) gCommander = id;
            removePerson(id);
            return;
        }
        if (!commander(id)) return;       // nothing else from anyone else
        gCommander = id;

        if (word == "status")
        {
            string playing = gMode;
            if (gMode != "still") playing += " " + gDance;
            if (gMode == "sequence" || gMode == "random") playing += " every " + (string)((integer)gSeconds) + " s";
            tell("ready (v" + VERSION + "): " + (string)llGetListLength(slots()) + " slots, "
                 + (string)llGetListLength(allDances()) + " dances, " + (string)llGetListLength(playlists())
                 + " playlists, using " + listLabel() + "; " + playing + "; " + who());
        }
        else if (word == "list")
        {
            if (llToLower(rest) == "all") sendItems("dances (all, " + (string)llGetListLength(allDances()) + ")", allDances());
            else sendItems("dances (" + listLabel() + ", " + (string)llGetListLength(dances()) + ")", dances());
        }
        else if (word == "lists")
        {
            list p = playlists();
            if (p == []) tell("no playlists in the prim (notecards named <something>.lst); using all dances");
            else sendItems("playlists (" + (string)llGetListLength(p) + ", using " + listLabel() + ")", p);
        }
        else if (word == "show" || word == "use")
        {
            if (word == "use" && (llToLower(rest) == "all" || rest == ""))
            {
                gListName = "";
                gPlaylist = [];
                gIndex = -1;
                tell("using all " + (string)llGetListLength(allDances()) + " dances");
                if (gDebug) llOwnerSay("dance_hud debug: playlist all dances (" + (string)llGetListLength(allDances()) + ")");
                return;
            }
            string card = findList(rest);
            if (card == "") { tell("no playlist \"" + rest + "\" (lists shows them)"); return; }
            readList(card, word);
        }
        else if (word == "who") tell(who());
        else if (word == "invite") invite(person(rest));
        else if (word == "remove")
        {
            key k = findDancer(rest);
            if (k == NULL_KEY) { tell("nobody dancing matches \"" + rest + "\" (who lists them)"); return; }
            removePerson(k);
        }
        else if (word == "me")
        {
            if (llToLower(rest) == "off") removePerson(AVATAR);
            else invite(person((string)AVATAR));
        }
        else if (word == "play")
        {
            list d = dances();
            string dance = findDance(rest);
            integer n = (integer)rest;
            if (dance == "")
            {
                if (n > 0 && n <= llGetListLength(d) && (string)n == rest) dance = llList2String(d, n - 1);
                else { tell("no dance \"" + rest + "\" (list all shows them)"); return; }
            }
            gMode = "play";
            gIndex = llListFindList(d, [dance]);
            llSetTimerEvent(0.0);
            play(dance);
            tell("playing " + dance);
        }
        else if (word == "sequence" || word == "random")
        {
            gSeconds = (float)rest;
            if (gSeconds < MIN_SECONDS) gSeconds = DEFAULT_SECONDS;
            gMode = word;
            gIndex = -1;
            next();
            llSetTimerEvent(gSeconds);
            tell(word + ", changing every " + (string)((integer)gSeconds) + " s; now " + gDance);
        }
        else if (word == "next")
        {
            if (gMode != "sequence" && gMode != "random") { tell("next works in sequence or random"); return; }
            next();
            llSetTimerEvent(gSeconds);
            tell("now " + gDance);
        }
        else if (word == "debug")
        {
            if (!owner(id)) { tell("debug is for owners"); return; }
            rest = llToLower(rest);
            if (rest == "on") gDebug = TRUE;
            else if (rest == "off") gDebug = FALSE;
            else gDebug = !gDebug;
            if (gDebug) { tell("debug on: each dance is announced to the owner as it starts"); sayNow(); }
            else tell("debug off");
        }
        else if (word == "stop")
        {
            gMode = "still";
            gDance = "";
            llSetTimerEvent(0.0);
            llMessageLinked(LINK_THIS, ALL_STOP, "", NULL_KEY);
            tell("stopped: everyone's standing still");
        }
        else tell("unknown command \"" + word + "\"");
    }

    link_message(integer sender, integer num, string str, key id)
    {
        if (num < FROM_SLOT || num >= SLOT_RELEASE) return;
        integer s = num - FROM_SLOT;
        if (str == "joined")
        {
            drop(id);
            gDancers += [s, id];
            string hint = "";
            if (gMode != "still") llMessageLinked(LINK_THIS, SLOT_PLAY + s, gDance, id);
            else hint = "; nothing's playing yet: play, sequence or random to start";
            notify(name(id) + " joined (" + (string)id + ")" + hint);
            debugSay(name(id) + " joined (slot " + (string)s + "); "
                     + (string)(llGetListLength(gDancers) / 2) + " dancing");
        }
        else
        {
            drop(id);
            string why = "stopped dancing";
            if (str == "declined") why = "said no to the invite";
            else if (str == "timeout") why = "didn't answer the invite";
            else if (str == "left") why = "dropped: left the region or stopped the animation";
            else if (str == "removed") why = "dropped (removed)";
            debugSay(name(id) + " " + why + " (slot " + (string)s + " free); "
                     + (string)(llGetListLength(gDancers) / 2) + " dancing");
            if (str == "declined") notify(name(id) + " said no");
            else if (str == "timeout") notify(name(id) + " didn't answer");
            else if (str == "left") notify(name(id) + " left the region or stopped the animation: slot freed");
            else notify(name(id) + " stopped dancing");
        }
    }

    timer()
    {
        next();
    }
}
