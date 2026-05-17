# Video Outline: Building Bespoke Software with AI

**Format:** Talking-head / screen share hybrid  
**Target length:** 3–5 minutes  
**Working title:** "The One-User App: What AI Makes Possible"

---

## The Big Idea (the through-line for the whole video)

SaaS products are built for the median user. They have to be — you can't justify engineering time for a feature that only 2% of users need. So every product compromises. It almost works for everyone, but it works perfectly for nobody.

AI changes that equation entirely. The cost of building software has collapsed. You can now commission a bespoke system — one that fits your exact workflow, your exact storage setup, your exact preferences — in hours rather than months. It may only ever have one user. That's fine. That's the point.

Camberbrick Green is an example of exactly this.

---

## What Camberbrick Green Is

A personal LEGO part manager, built entirely for one person's specific storage system.

**The problem it solves:**
- Large LEGO collections need organisation. Commercial solutions (Bricklink, Rebrickable, BrickArchitect) are catalogues — they tell you what a part *is*, not where *your* copy of it lives.
- Generic inventory apps don't understand the LEGO-specific concepts: part numbers, minifigures, categories, storage drawer systems like Akro-Mils.
- The storage system is personal. One person uses 64-drawer Akro-Mils units for high-frequency parts, bead boxes and shoe boxes for the long tail. No SaaS product will ever model that.

**What the app actually does:**
- Photograph a LEGO piece with your phone → AI identifies it via Brickognize
- Look up the part's name and category from BrickArchitect
- Record exactly which physical drawer or bag it lives in
- Print a correctly-sized Brother P-touch label for that drawer — Small (2″ for Akro-Mils 64-drawer), Medium (4.5″ for 24-drawer), Large for shoeboxes
- Browse the full collection by BrickArchitect category
- Track minifigures separately, grouped by theme
- Home screen shows what was most recently added (or a daily spotlight if nothing new)
- Overflow locations — when you have a lot of a part and it spills into a second drawer, you can record that too

**The key philosophical point:** Every single one of these features exists because *one* person needed it, exactly that way. A SaaS product would have shipped a generic "add location" field and called it done.

---

## The AI-First Development Story

This is the second angle of the video: *how* it was built.

**Tools used:**
- **Claude Code** — the CLI that lets you have a conversation with Claude about your codebase. You describe what you want, it reads the relevant files, writes the code, runs the tests, and commits.
- **Claude Co-work** — the collaborative interface where you can point at a project and work on it together in longer sessions.

**What the workflow actually looks like:**
- No ticket system, no sprint planning, no handoff between designer and developer
- Describe a feature in plain English ("I want to be able to add an overflow location to a part")
- Claude explores the codebase, identifies the right files, proposes the approach, asks clarifying questions where it matters
- Code is written, verified in a browser preview, committed, and pushed — all in the same conversation
- Features that would have taken a freelancer a day or two take 20–30 minutes

**Specific examples from this build worth showing:**
- The label printing system: downloading `.lbx` files from BrickArchitect, patching the XML to retarget the printer and resize the content for 24mm tape, calling an AppleScript to trigger the print — all described conversationally and built incrementally
- The overflow location feature: the database already had a many-to-many schema for this (part_locations with a `role` column), but the UI only exposed one location. One conversation added the add/remove buttons, the HTMX inline updates, the filtered dropdown, and the backend routes
- The print size picker: started as auto-detection from storage type, pivoted mid-conversation to manual Small/Medium/Large buttons — the whole change took minutes, not a day of back-and-forth with a developer

---

## Suggested Video Structure

### 0:00 – 0:30 | Hook
Open on the app running on a phone. Scan a LEGO part. Watch it identify, show the location, offer to print a label.

"This app has exactly one user. Me. And it does exactly what I need — nothing more, nothing less."

### 0:30 – 1:30 | The Problem with SaaS
- Every SaaS product tries to be everything to everyone
- End up with feature bloat that serves the majority, not you
- The storage problem: Rebrickable can tell you what part 3001 is, it cannot tell you it's in drawer 14 of your Akro-Mils unit in the garage
- Your system is *yours* — part numbers you care about, storage units you actually own, label sizes that fit your drawers

### 1:30 – 2:30 | What Camberbrick Green Does
Walk through the app:
- Scan a part → identify → see location
- Browse by category
- Minifigures page
- Part detail: primary + overflow locations, print label (show the size options)
- Home screen cards

### 2:30 – 3:30 | How It Was Built
- Introduce Claude Code / Claude Co-work
- Show or describe the conversation-driven workflow
- Key insight: Claude understands the *codebase*, not just the current question. It reads the existing routes, templates, and database schema before writing anything.
- The cost of a feature is now the time it takes to describe it clearly

### 3:30 – 4:30 | The Bigger Idea
- AI hasn't just made developers faster — it's made non-developers into builders
- The one-user app is now a viable thing. Build exactly what you need.
- You could do this for: your recipe collection, your book catalogue, your workshop inventory, your plant care schedule — anything where generic apps almost work but never quite do
- The question is no longer "is there an app for that?" — it's "what do I actually want?"

### 4:30 – 5:00 | Close
- Show the finished label being printed, going on a drawer
- "This took hours, not months. It'll never be on the App Store. It doesn't need to be."

---

## Tone Notes

- Conversational, not a tutorial
- The audience is curious non-developers and developers who haven't tried AI-assisted building yet
- Avoid jargon where possible; when technical terms come up (HTMX, FastAPI, SQLite), name-drop them but don't explain them — the point is the outcome, not the stack
- The LEGO angle is charming and relatable — lean into it, don't apologise for it being a "small" problem

---

## Possible Screen Recording Moments

- Typing a feature request into Claude Code → watching it read files and write code
- The browser preview updating live after a code change
- Scanning a physical LEGO part with the phone camera
- The label printing: clicking "Small", hearing the printer, pulling the label off
- The overflow location add/remove working inline without a page reload

---

## Key Quotes / Lines to Work In

- "It has one user. That's fine. That's the point."
- "SaaS tries to be generalist. It ends up being good enough for nobody."
- "I described what I wanted in plain English. Twenty minutes later it was in production."
- "The barrier used to be 'can someone build this?' Now it's 'do I want this enough to describe it?'"
