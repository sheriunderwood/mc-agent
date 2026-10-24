// dance_slot: one dancer's slot for dance_hud.
//
// A script can animate only one avatar, so the prim needs one copy of this
// script per dancer. Drop in as many copies as you like; SL names them
// "dance_slot-v1.0.0", "dance_slot-v1.0.0 1", "... 2"... and that number is the slot.
//
// Experience: compile this script with the prim owner's experience (in the script
// editor, tick "Use Experience" and pick it, then Save) and anyone who has
// accepted that experience joins without a permission box. Without it, or for
// someone who hasn't accepted the experience, the usual "would like to animate
// your avatar" box asks them instead.

string VERSION = "1.0.1";   // semantic version: see scripts/README.md
integer ALL_PLAY = 1;
integer ALL_STOP = 2;
integer ALL_RELEASE = 5;
integer SLOT_INVITE = 1000;
integer FROM_SLOT = 2000;
integer SLOT_RELEASE = 3000;
integer SLOT_PLAY = 4000;
float ANSWER_WAIT = 60.0;   // seconds to wait for a yes
float CHECK_EVERY = 10.0;   // seconds between "still here?" checks

integer gSlot;
key gWho;
string gDance = "";
integer gWaiting;
float gAsked;     // when the invite went out (llGetTime)

// The slot number at the end of a dance_slot script's name: "dance_slot-v1.0.0 3"
// (or "dance_slot 3") is 3; the first copy, with no number, is 0.
integer slotNumber(string script)
{
    list parts = llParseString2List(script, [" "], []);
    string last = llList2String(parts, -1);
    if (llGetListLength(parts) > 1 && (string)((integer)last) == last) return (integer)last;
    return 0;
}

report(string what)
{
    llMessageLinked(LINK_THIS, FROM_SLOT + gSlot, what, gWho);
}

integer canAnimate()
{
    return gWho != NULL_KEY && llGetPermissionsKey() == gWho
        && (llGetPermissions() & PERMISSION_TRIGGER_ANIMATION);
}

stopDance()
{
    if (gDance != "" && canAnimate()) llStopAnimation(gDance);
    gDance = "";
}

dance(string d)
{
    if (!canAnimate()) return;
    stopDance();
    gDance = d;
    llStartAnimation(gDance);
}

joined()
{
    gWaiting = FALSE;
    llSetTimerEvent(CHECK_EVERY);
    report("joined");
}

finish(string why)
{
    stopDance();
    report(why);
    llResetScript();   // lets go of the permission
}

default
{
    state_entry()
    {
        gSlot = slotNumber(llGetScriptName());
    }

    link_message(integer sender, integer num, string str, key id)
    {
        if (num == SLOT_INVITE + gSlot)
        {
            gWho = id;
            gWaiting = TRUE;
            gAsked = llGetTime();
            llSetTimerEvent(CHECK_EVERY);
            llRequestExperiencePermissions(id, "");
        }
        else if (num == SLOT_RELEASE + gSlot) finish("removed");
        else if (num == SLOT_PLAY + gSlot || num == ALL_PLAY) dance(str);
        else if (num == ALL_STOP) stopDance();
        else if (num == ALL_RELEASE) { stopDance(); llResetScript(); }   // dance_hud started over
    }

    experience_permissions(key agent)
    {
        joined();
    }

    experience_permissions_denied(key agent, integer reason)
    {
        // They turned the experience down: that's a no. Anything else (no
        // experience on this script, not allowed on this land...): ask the usual way.
        if (reason == XP_ERROR_NOT_PERMITTED) finish("declined");
        else llRequestPermissions(agent, PERMISSION_TRIGGER_ANIMATION);
    }

    run_time_permissions(integer perm)
    {
        if (!gWaiting) return;
        if (perm & PERMISSION_TRIGGER_ANIMATION) joined();
        else finish("declined");
    }

    timer()
    {
        // Left the region (or stopped the animation): drop them, freeing the slot.
        if (gWaiting)
        {
            if (llGetAgentSize(gWho) == ZERO_VECTOR || llGetTime() - gAsked > ANSWER_WAIT) finish("timeout");
        }
        else if (llGetAgentSize(gWho) == ZERO_VECTOR || !canAnimate()) finish("left");
    }
}
