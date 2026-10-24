# The HUD scripts

Two optional LSL tools for your avatar:

| Script | What it does |
|--------|--------------|
| `dance_hud` + `dance_slot` | A **dance HUD** in a prim at your club: everyone dancing moves in sync, with playlists, invitations and a debug mode. The avatar drives it with its `dance` tool. |
| `wearing` | A **"what are they wearing" HUD** the avatar wears: reads the attachments of people within 20 m and saves them, so the avatar can compliment outfits and ask where they're from. |

**Don't paste these files into a script by hand.** They contain placeholders
like `@@OWNERS@@`. Ask your avatar instead: it makes a copy with your avatar's
UUID, your owners (OWNERS.md), the channels (`[huds]` in config.toml) and your
home region and parcel filled in, compiles it, and gives it to you. Only an
owner can ask, by IM:

> install the dance_hud script, then give it to me

Both scripts only take commands from your avatar and its owners (checked by
UUID, never by name), and only animate people who agreed.

## Versions

Each script has a [semantic version](https://semver.org) near the top
(`string VERSION = "x.y.z";`), and its copies are named with it, e.g.
`dance_hud-v1.4.0`, so old copies are easy to spot. The avatar's
`tidy_scripts` tool clears out old versions from its inventory. When you
update the scripts in a prim, take the old versions out.

## Setting up the dance HUD

### 1. Get the scripts

IM your avatar:

> install the dance_hud script, then give it to me
> install the dance_slot script, then give it to me

Accept both.

### 2. Optional: compile `dance_slot` with your experience

So that people who've accepted your experience can join without a permission
box:

1. Open `dance_slot`, tick **Use Experience**, choose your experience, and
   **Save**.
2. Make sure the experience is allowed on the land: About Land → Experiences →
   Allowed.

Without this, everything still works: each dancer gets the usual "would like to
animate your avatar" box.

### 3. Fill a prim

1. Rez a prim near where your avatar stands (or use one that's there), edit it
   (Ctrl+3) → Content.
2. Drag in `dance_hud`.
3. Drag in `dance_slot` **once per dancer** you want at the same time,
   counting your avatar if it dances too. Eight is a good start. SL names the
   copies `dance_slot-v1.0.1 1`, `dance_slot-v1.0.1 2`… and the HUD counts
   them. If copying loses the experience, compile each copy as in step 2.
4. Drag in the **dances** (animations). A prim's contents have no folders:
   every animation in it is a dance, in name order. With none, the built-in
   dance1 to dance8 are used.

### 4. Optional: playlists

A playlist is a **notecard in the prim** named `<something>.lst` (say
`calm_dances.lst`), one dance name per line, exactly as the animation is named.
Blank lines and lines starting with `#` are skipped.

- Ask your avatar to make one: "make a calm_dances list with Slow Sway and
  Peach Dance". It checks the names, saves the notecard in its **Dance lists**
  folder and can give it to you; drop it into the prim.
- Or write the notecard yourself.

### 5. Check it

Near the prim, type `/34336status` (34336 is the default `[huds]
dance_channel`). You should get `dance_hud: ready: 8 slots, N dances, …`.

### Commands

Your avatar uses these through its `dance` tool; owners can type them too,
near the prim (`/34336who`):

- `list`, `list all`, `lists`, `show <list>`, `use <list>` / `use all`
- `play <number or name>`, `sequence [seconds]`, `random [seconds]`, `next`, `stop`
- `me on` / `me off`: the avatar dances too, or stands still
- `invite <uuid>`: the agent only lets the avatar invite friends or owners who
  are in the region and said yes
- `who`, `remove <uuid, part of a name, or slot>`
- `debug` (owners): hear each dance as it starts, and each invite, join and drop
- Anyone dancing can stop: `/34336leave`, or `/99stop` as with other dance HUDs.
  Someone who leaves the region is dropped within about 10 seconds.

## Setting up the wearing HUD

Scripts can see the attachments of anyone in the region (not their HUDs, and
not system clothing or BOM layers), the same as the "What is she wearing?" HUDs
on the Marketplace.

1. IM your avatar: "install the wearing script, then give it to me".
2. Rez a small cube (0.05 m, transparent if you like), name it, say,
   **`wearing HUD`**, and drop the script in.
3. **Wear it on your own HUD once** (right-click → Attach to HUD → Top
   Right), then detach it, so it remembers the HUD point. While you wear it,
   it talks to you; that's fine.
4. Take it into your inventory and **give it to your avatar**; it accepts
   owners' gifts itself.
5. IM your avatar: "wear the wearing HUD".

What happens then:

- **Only within 20 m**, so a crowded club doesn't mean dozens of scans.
- **At home** (the region and parcel in config.toml): it scans the avatar's own
  outfit a minute after it's attached, then each person who comes within 20 m,
  30 s later so their outfit has rezzed; nobody more than once an hour.
- **Elsewhere** it only scans when an owner asks the avatar ("what's Pixel
  wearing?"); they must be within 20 m.
- It sends one message every 10 s, under Morgen Commander's limit of 10 object
  lines a minute; a typical outfit takes 2–4 messages.
- The agent's program (not the AI) saves the result in the data folder:
  `friends/<name>/wearing-YY-MM-DD-HH-mm.md` for people the avatar knows,
  `wearing/<name>-…md` for anyone else. It only accepts scans from a HUD the
  avatar owns, and never saves blocked people.

Commands, from the avatar or an owner, on channel 34337 (the default `[huds]
wearing_channel`): `status`, `scan <name or uuid>`, `scan` (everyone within
20 m, at home), `auto on` / `auto off`, `debug` (an owner follows along
privately).
