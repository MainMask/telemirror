"""Setup mirrors: create, configure, verify, and build Telegram mirror configuration."""

import asyncio
import io
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    DeleteChannelRequest,
    EditPhotoRequest,
    EditTitleRequest,
    ToggleForumRequest,
)
from telethon.tl.functions.messages import (
    CreateForumTopicRequest,
    EditForumTopicRequest,
)
from telethon.tl.types import ChatPhotoEmpty, InputChatUploadedPhoto

from skylon_set._common import entity_type, fetch_all_topics, make_client, safe_call

CONFIG_PATH = Path(__file__).resolve().parent.parent / ".configs" / "mirror.config.yml"

MENU_ACTIONS = [
    ("full-cycle",   "Full cycle",        "create → configure → verify → config → final"),
    ("create-pairs", "Create pairs",      "recipients for donors without a pair"),
    ("configure",    "Configure",         "avatars + topic emoji + General visibility"),
    ("verify",       "Verify",            "pairs, dupes → mark → delete"),
    ("build-config", "Build config",      "generate mirror.config.yml"),
    ("final-verify", "Final verification", "reconcile titles, fix discrepancies"),
]

_SEP = "─" * 72


def show_menu() -> str:
    print("\n=== TELEMIRROR ===\n")
    action, name, desc = MENU_ACTIONS[0]
    print(f"  1. {name:<22} [{desc}]")
    print(f"  {_SEP}")
    for i, (_, name, desc) in enumerate(MENU_ACTIONS[1:], 2):
        print(f"  {i}. {name:<22} [{desc}]")
    print(f"  {_SEP}")
    print("  0. Exit\n")
    while True:
        choice = input("Choose an action: ").strip()
        if choice == "0":
            sys.exit(0)
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(MENU_ACTIONS):
                return MENU_ACTIONS[idx][0]
        except ValueError:
            pass
        print(f"  Enter a number from 0 to {len(MENU_ACTIONS)}")


# ── Utilities ────────────────────────────────────────────────────────────────

_DE_SKLAD_VARIANTS = ("DÈ SKLAD", "DÉ SKLAD", "DE SKLAD")

_CITADEL_SUFFIX = "⚜️ Цитадель"
_PIRATE_FLAG = "🏴‍☠️"

# A "🏴‍☠️ DÈ SKLAD" trailer at the end of the title (the flag and spacing are optional).
_DONOR_TRAILER_RE = re.compile(
    r"\s*(?:" + re.escape(_PIRATE_FLAG) + r"\s*)?(?:"
    + "|".join(re.escape(v) for v in _DE_SKLAD_VARIANTS)
    + r")\s*$"
)


def has_de_sklad(title: str) -> bool:
    return any(v in title for v in _DE_SKLAD_VARIANTS)


def to_citadel(title: str) -> str:
    """Donor title → recipient title.

    Strips a "🏴‍☠️ DÈ SKLAD" trailer and appends "⚜️ Цитадель". Titles with no
    trailer (e.g. "Activity | …") simply get the suffix appended.
    """
    return f"{_DONOR_TRAILER_RE.sub('', title).rstrip()} {_CITADEL_SUFFIX}"


_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FFFF\U00002600-\U000027BF︀-️‍]+"
)


def name_key(title: str) -> str:
    """Strip brand keyword and emoji, return just the name part for fuzzy matching."""
    for v in (*_DE_SKLAD_VARIANTS, "Цитадель"):
        if v in title:
            title = title.replace(v, "")
            break
    return _EMOJI_RE.sub("", title).strip()


# ── Donor classification: live (past + live) vs courses (past_mode only) ──────
#
# Names are exactly as they appear in the owner's dialogs. Live donors stay in
# .configs/mirror.config.yml; courses go to a separate citadel_courses.config.yml,
# which only past_mode.py reads. Anything found matching "DE SKLAD" but not in
# either list is printed by the script and left untouched.

_LIVE_DONOR_TITLES = [
    "СЛЕЗЫ САТОШИ 🏴‍☠️ DÈ SKLAD",
    "BILLIONS CRYPTO 🏴‍☠️ DÈ SKLAD",
    "pepe.research 🏴‍☠️ DÈ SKLAD",
    "CRYPTO ANGEL 🏴‍☠️ DÈ SKLAD",
    "INSTARDING 🏴‍☠️ DÉ SKLAD",
    "MM TRADERS 🏴‍☠️ DÈ SKLAD",
    "VECTRUM CLUB 🏴‍☠️DÈ SKLAD",
    "INSTARDING PRO TRADING 🏴‍☠️ DÉ SKLAD",
    "shitpost padre 🏴‍☠️ DÉ SKLAD",
    "Pentagon Pro 🏴‍☠️ DE SKLAD",
    "SmartCapital 🏴‍☠️ DÈ SKLAD",
    "Rose 🏴‍☠️ DÈ SKLAD",
]

_COURSE_DONOR_TITLES = [
    "Maloletoff Education 2024 🏴‍☠️ DÈ SKLAD",
    "CRYPTOLOGY 🏴‍☠️ DÈ SKLAD",
    "SANCHO 🏴‍☠️ DÈ SKLAD",
    "Jay Education 🏴‍☠️ DÈ SKLAD",
    "Mozart Academy 🏴‍☠️ DÈ SKLAD",
    "Cryptomannn 2023 🏴‍☠️ DÈ SKLAD",
    "a01k Academy 🏴‍☠️ DÈ SKLAD",
    "Activity | Начинающий дропхантер",
    "MM ACADEMY 🏴‍☠️ DÈ SKLAD",
    "Block13 🏴‍☠️ DÈ SKLAD",
    "CRYPTOLOGY WORKSHOP 🏴‍☠️ DÈ SKLAD",
    "DEXMEN EDUCATION 🏴‍☠️ DÈ SKLAD",
    "Meme bootcamp 2.0 🏴‍☠️ DÈ SKLAD",
    "DYOR Pentagon 5.0 🏴‍☠️ DÉ SKLAD",
    "DAYTRADING ACADEMY 🏴‍☠️ DÈ SKLAD",
    "Vectrum Обучение 🏴‍☠️ DÈ SKLAD",
    "DeFi Crypto 🏴‍☠️ DÈ SKLAD",
    "Activity | Курс для новичков 2024",
    "Обучение от КОВЧЕГА 🏴‍☠️ DÈ SKLAD",
    "A01K Academy 2.0 🏴‍☠️ DÉ SKLAD",
    "DarkTrader 3.0 🏴‍☠️ DÈ SKLAD",
    "Dyor Pentagon Education 🏴‍☠️ DÈ SKLAD",
    "Meme bootcamp (ноябрь) 🏴‍☠️ DÈ SKLAD",
]

_LIVE_KEYS = {name_key(t).casefold() for t in _LIVE_DONOR_TITLES}
_COURSE_KEYS = {name_key(t).casefold() for t in _COURSE_DONOR_TITLES}
assert _LIVE_KEYS.isdisjoint(_COURSE_KEYS), (
    f"live and course lists overlap: {_LIVE_KEYS & _COURSE_KEYS}"
)


def classify_donor(title: str) -> str:
    """"live" / "course" / "unknown" by the lists above (matched via name_key).

    An already-created "⚜️ Цитадель" recipient is never a donor: its name_key
    matches the donor's, so exclude by the brand in the title instead.
    """
    if "Цитадель" in title:
        return "unknown"
    key = name_key(title).casefold()
    if key in _LIVE_KEYS:
        return "live"
    if key in _COURSE_KEYS:
        return "course"
    return "unknown"


def find_recipient(expected: str, recipients: dict):
    """Exact title match first; fall back to matching by name (brand + emoji stripped)."""
    if expected in recipients:
        return recipients[expected]
    key = name_key(expected)
    if key:
        for title, dlg in recipients.items():
            if name_key(title) == key:
                return dlg
    return None


def full_id(entity) -> int:
    return int(f"-100{entity.id}")


def get_all_donors(dialogs) -> list:
    """Donors from the hardcoded lists (live + courses) found among the dialogs."""
    return sorted(
        [d for d in dialogs if classify_donor(d.title or "") != "unknown"],
        key=lambda d: d.title or "",
    )


def report_unmatched(dialogs) -> None:
    """Prints "DE SKLAD" dialogs that are in neither list (left untouched)."""
    unmatched = [
        d.title
        for d in dialogs
        if has_de_sklad(d.title or "") and classify_donor(d.title or "") == "unknown"
    ]
    if unmatched:
        print(f"\nOutside the lists ({len(unmatched)}, skipping):")
        for title in sorted(unmatched):
            print(f"  ? '{title}'")


def build_recipient_index(dialogs) -> dict:
    """title → dialog for all "Цитадель"-named dialogs (last wins on collision)."""
    return {d.title: d for d in dialogs if "Цитадель" in (d.title or "")}


async def get_premium_status(client) -> bool:
    me = await client.get_me()
    return bool(getattr(me, "premium", False))


# ── Step 1: Create pairs ───────────────────────────────────────────────────────

async def _sync_forum_topics(client, donor_e, recip_e, *, enable_forum: bool) -> None:
    """Creates every donor topic (id != 1) at the recipient that's missing by title.

    Idempotent: re-running after a FloodWait abort fills in the remaining topics.
    """
    if enable_forum:
        print("    Enabling forum...")
        await safe_call(client,
            lambda: client(ToggleForumRequest(channel=recip_e, enabled=True, tabs=False))
        )

    donor_topics = await fetch_all_topics(client, donor_e)
    recip_titles = {t.title for t in await fetch_all_topics(client, recip_e)}
    for topic in donor_topics:
        if topic.id == 1 or topic.title in recip_titles:
            continue
        print(f"    Creating topic '{topic.title}'...")
        await safe_call(client,
            lambda t=topic: client(
                CreateForumTopicRequest(peer=recip_e, title=t.title, icon_color=t.icon_color)
            )
        )


async def step_create_pairs(client):
    print("\n=== STEP 1: CREATE PAIRS ===\n")
    dialogs = await client.get_dialogs()
    donors = get_all_donors(dialogs)
    recipients = build_recipient_index(dialogs)
    report_unmatched(dialogs)

    missing = []
    for donor in donors:
        expected = to_citadel(donor.title)
        dtype = entity_type(donor.entity)
        if dtype == "other":
            continue
        rec = find_recipient(expected, recipients)
        if rec and entity_type(rec.entity) == dtype:
            print(f"OK:      '{donor.title}'  →  '{expected}'")
            # the recipient may be missing some topics (a previous run aborted)
            if getattr(donor.entity, "forum", False):
                if getattr(rec.entity, "forum", False):
                    await _sync_forum_topics(
                        client, donor.entity, rec.entity, enable_forum=False
                    )
                else:
                    print("    ⚠ recipient is not a forum — topics not synced")
        else:
            found = entity_type(rec.entity) if rec else None
            note = f" (found as {found}, not {dtype})" if found else " (not found)"
            print(f"MISSING: '{donor.title}'  →  '{expected}'{note}")
            missing.append(donor)

    if not missing:
        print("\nAll pairs are in place.")
        return

    print(f"\nCreating {len(missing)} recipient(s)...")
    for donor in missing:
        new_title = to_citadel(donor.title)
        e = donor.entity
        is_broadcast = getattr(e, "broadcast", False)
        is_megagroup = getattr(e, "megagroup", False)

        if not is_broadcast and not is_megagroup:
            print(f"  SKIP '{new_title}': neither a channel nor a supergroup")
            continue

        kind = "channel" if is_broadcast else "supergroup"
        print(f"  Creating {kind} '{new_title}'...")
        result = await safe_call(client,
            lambda t=new_title, b=is_broadcast, m=is_megagroup: client(
                CreateChannelRequest(title=t, about="", broadcast=b, megagroup=m)
            )
        )
        if result is None:
            print(f"    Failed to create '{new_title}'")
            continue

        created = result.chats[0]
        print(f"    Created: id={full_id(created)}  '{created.title}'")

        if is_megagroup and getattr(e, "forum", False):
            await _sync_forum_topics(client, e, created, enable_forum=True)

    print("Done.")


# ── Step 2: Configure ────────────────────────────────────────────────────────

async def step_configure(client):
    print("\n=== STEP 2: CONFIGURE ===\n")
    premium = await get_premium_status(client)
    print(f"Premium status: {'yes' if premium else 'no'}\n")

    dialogs = await client.get_dialogs()
    donors = get_all_donors(dialogs)
    recipients = build_recipient_index(dialogs)
    topic_cache: dict = {}

    async def fetch_topics(entity) -> dict:
        eid = entity.id
        if eid not in topic_cache:
            topic_cache[eid] = {
                t.id: t for t in await fetch_all_topics(client, entity)
            }
        return topic_cache[eid]

    for donor in donors:
        expected = to_citadel(donor.title)
        recipient = find_recipient(expected, recipients)
        if not recipient:
            print(f"SKIP '{donor.title}': recipient '{expected}' not found")
            continue

        print(f"'{donor.title}'  →  '{recipient.title}'")
        d_entity = donor.entity
        r_entity = recipient.entity

        # Avatar
        if isinstance(r_entity.photo, ChatPhotoEmpty):
            buf = io.BytesIO()
            ok = await client.download_profile_photo(d_entity, file=buf, download_big=True)
            if ok is None:
                print("  Avatar: donor has none")
            else:
                buf.seek(0)
                uploaded = await client.upload_file(buf, file_name="photo.jpg")
                await safe_call(client,
                    lambda re=r_entity, u=uploaded: client(
                        EditPhotoRequest(channel=re, photo=InputChatUploadedPhoto(file=u))
                    )
                )
                print("  Avatar: copied")
        else:
            print("  Avatar: already set")

        # Topics (forum supergroups only)
        if not getattr(d_entity, "forum", False):
            continue

        d_topics = await fetch_topics(d_entity)
        r_topics = await fetch_topics(r_entity)
        r_by_title = {t.title: t for t in r_topics.values()}

        for d_topic in d_topics.values():
            r_topic = r_topics.get(1) if d_topic.id == 1 else r_by_title.get(d_topic.title)
            if not r_topic:
                print(f"  Topic '{d_topic.title}': not found at recipient")
                continue

            # Emoji
            d_emoji = d_topic.icon_emoji_id or 0
            r_emoji = r_topic.icon_emoji_id or 0
            if d_emoji != r_emoji:
                if not premium and d_emoji != 0:
                    print(f"  Topic '{d_topic.title}': no Premium for the emoji")
                else:
                    await safe_call(client,
                        lambda re=r_entity, rid=r_topic.id, eid=d_emoji: client(
                            EditForumTopicRequest(peer=re, topic_id=rid, icon_emoji_id=eid)
                        )
                    )
                    print(f"  Topic '{d_topic.title}': emoji updated")

            # General topic visibility and title
            if d_topic.id == 1:
                if d_topic.title != r_topic.title:
                    await safe_call(client,
                        lambda re=r_entity, t=d_topic.title: client(
                            EditForumTopicRequest(peer=re, topic_id=1, title=t)
                        )
                    )
                    print(f"  General: renamed to '{d_topic.title}'")
                d_hidden = bool(getattr(d_topic, "hidden", False))
                r_hidden = bool(getattr(r_topic, "hidden", False))
                if d_hidden != r_hidden:
                    await safe_call(client,
                        lambda re=r_entity, h=d_hidden: client(
                            EditForumTopicRequest(peer=re, topic_id=1, hidden=h)
                        )
                    )
                    print(f"  General: {'hidden' if d_hidden else 'shown'}")

    print("\nConfiguration complete.")


# ── Step 3: Verify ───────────────────────────────────────────────────────────

async def step_verify(client):
    print("\n=== STEP 3: VERIFY PAIRS AND DUPES ===\n")
    dialogs = await client.get_dialogs()
    donors = get_all_donors(dialogs)
    recipients = build_recipient_index(dialogs)

    # Verify pairs
    print("--- Pairs ---\n")
    for donor in donors:
        expected = to_citadel(donor.title)
        dtype = entity_type(donor.entity)
        kind = classify_donor(donor.title)
        rec = find_recipient(expected, recipients)
        if rec and entity_type(rec.entity) == dtype:
            print(f"OK      [{kind}]: '{donor.title}'  →  '{expected}'")
        else:
            found = entity_type(rec.entity) if rec else None
            note = f" (found as {found}, not {dtype})" if found else " (not found)"
            print(f"MISSING [{kind}]: '{donor.title}'  →  '{expected}'{note}")

    report_unmatched(dialogs)

    # Look for duplicate "Цитадель"-named dialogs
    print("\n--- Dupes ---\n")
    known_ids: set[int] = set()
    for path in (CONFIG_PATH, COURSES_CONFIG_PATH):
        if path.exists():
            with open(path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            for d in cfg.get("directions", []):
                known_ids.add(int(str(d["to"][0]).split("#")[0]))

    groups: dict[str, list] = defaultdict(list)
    for dlg in dialogs:
        title = dlg.title or ""
        key = name_key(title)
        # an empty key = the title is exactly "Цитадель" (the brand cut out
        # entirely): such channels would collapse into one false group
        if key and "Цитадель" in title and not title.startswith("[DUPLICATE]"):
            groups[key].append(dlg)

    extras = []
    any_dupe = False
    for dlgs in groups.values():
        if len(dlgs) <= 1:
            continue
        any_dupe = True
        titles = {d.title for d in dlgs}
        label = "DUPLICATE" if len(titles) == 1 else "POTENTIAL DUPLICATE"
        real  = [d for d in dlgs if full_id(d.entity) in known_ids] or dlgs[:1]
        extra = [d for d in dlgs if d not in real]
        print(f'{label}: {" / ".join(f"\"{t}\"" for t in sorted(titles))}')
        for d in real:
            print(f"  [keep]    id={full_id(d.entity)}  '{d.title}'")
        for d in extra:
            print(f"  [extra]   id={full_id(d.entity)}  '{d.title}'")
            extras.append(d)

    if not any_dupe:
        print("No dupes found.")

    if extras:
        answer = input(f"\nMark {len(extras)} extra one(s) as [DUPLICATE]? [y/N]: ").strip().lower()
        if answer == "y":
            for dlg in extras:
                new_name = f"[DUPLICATE] {dlg.title}"
                print(f'  "{dlg.title}" → "{new_name}"...')
                await safe_call(client,
                    lambda e=dlg.entity, t=new_name: client(EditTitleRequest(channel=e, title=t))
                )

    # Delete marked ones (including any already marked before this run)
    marked = [d for d in await client.get_dialogs() if (d.title or "").startswith("[DUPLICATE]")]
    if not marked:
        print("\nNo objects marked [DUPLICATE].")
        return

    print(f"\nFound {len(marked)} object(s) marked [DUPLICATE]:")
    for dlg in marked:
        print(f"  {full_id(dlg.entity)}  '{dlg.title}'")

    answer = input("\nDelete them? This is irreversible! [y/N]: ").strip().lower()
    if answer != "y":
        return

    deleted = 0
    for dlg in marked:
        print(f'  Deleting "{dlg.title}"...')
        result = await safe_call(client, lambda e=dlg.entity: client(DeleteChannelRequest(channel=e)))
        if result is not None:
            deleted += 1
    skipped = len(marked) - deleted
    print(f"Deleted {deleted}." + (f" Skipped {skipped} (no access — delete manually)." if skipped else ""))


# ── Step 4: Build config ─────────────────────────────────────────────────────

def _direction(frm, to) -> dict:
    """One direction with `past_mode: full_history` (a fresh dict — no YAML aliases)."""
    return {"from": [frm], "to": [to], "past_mode": {"full_history": True}}


def _dir_key(d: dict) -> tuple:
    return (
        tuple(str(x) for x in d["from"]),
        tuple(str(x) for x in d["to"]),
    )


def _append_directions_text(config_path: Path, original: str, fresh: list) -> None:
    """Append `fresh` to the end of the `directions:` block, preserving the file's comments.

    Requires `directions:` to be the last top-level key (as it is in
    .configs/mirror.config.yml).
    """
    lines = original.splitlines()
    top_keys = [i for i, ln in enumerate(lines) if re.match(r"[A-Za-z_][\w-]*:", ln)]
    if not top_keys or not lines[top_keys[-1]].startswith("directions:"):
        raise ValueError(
            "directions: is not the last top-level key — appending is unsafe, "
            "edit the config by hand"
        )
    block = yaml.safe_dump(
        fresh, allow_unicode=True, default_flow_style=False, sort_keys=False
    )
    sep = "" if original.endswith("\n") else "\n"
    config_path.write_text(original + sep + block, encoding="utf-8")


def write_directions(
    config_path: Path, directions: list, *, merge: bool = False
) -> Path | None:
    """Writes `directions` to the config, keeping the other keys.

    `merge=False` (default) — replaces the `directions` key wholesale (the
    file's comments are lost). `merge=True` — appends only the new directions
    (deduped by from→to) to the end of the `directions:` block as text,
    preserving comments.

    If the file exists, makes a `.bak` and returns its path.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if not config_path.exists():
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                {"directions": directions}, f,
                allow_unicode=True, default_flow_style=False, sort_keys=False,
            )
        return None

    original = config_path.read_text(encoding="utf-8")
    backup = config_path.with_suffix(config_path.suffix + ".bak")
    backup.write_text(original, encoding="utf-8")

    if not merge:
        existing = yaml.safe_load(original) or {}
        existing["directions"] = directions
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                existing, f,
                allow_unicode=True, default_flow_style=False, sort_keys=False,
            )
        return backup

    existing = yaml.safe_load(original) or {}
    seen = {_dir_key(d) for d in (existing.get("directions") or [])}
    fresh = [d for d in directions if _dir_key(d) not in seen]
    if not fresh:
        backup.unlink()
        return None
    _append_directions_text(config_path, original, fresh)
    return backup


COURSES_CONFIG_PATH = CONFIG_PATH.parent / "citadel_courses.config.yml"


def write_courses_config(course_dirs: list) -> Path | None:
    """Writes citadel_courses.config.yml: the global block from mirror.config.yml
    (without broadcast_*) + the course directions. Only past_mode.py reads this file."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        main_cfg = yaml.safe_load(f) or {}
    carry = {
        k: main_cfg[k]
        for k in ("disable_edit", "disable_delete", "fallback_link_url", "filters")
        if k in main_cfg
    }
    carry["directions"] = course_dirs

    backup: Path | None = None
    if COURSES_CONFIG_PATH.exists():
        backup = COURSES_CONFIG_PATH.with_suffix(COURSES_CONFIG_PATH.suffix + ".bak")
        backup.write_text(
            COURSES_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8"
        )

    header = (
        "# Generated by skylon_set/setup_mirrors.py — «⚜️ Цитадель» courses.\n"
        "# main.py does NOT read this file; courses are only replayed through history:\n"
        '#   YAML_CONFIG_ENV="$(cat .configs/citadel_courses.config.yml)" python past_mode.py\n\n'
    )
    body = yaml.safe_dump(
        carry, allow_unicode=True, default_flow_style=False, sort_keys=False
    )
    COURSES_CONFIG_PATH.write_text(header + body, encoding="utf-8")
    return backup


async def step_build_config(client):
    print("\n=== STEP 4: BUILD CONFIG ===\n")
    dialogs = await client.get_dialogs()
    donors = get_all_donors(dialogs)
    recipients = build_recipient_index(dialogs)

    live_dirs: list = []
    course_dirs: list = []
    missing = []

    for donor in donors:
        e = donor.entity
        expected = to_citadel(donor.title)
        rec = find_recipient(expected, recipients)
        kind = classify_donor(donor.title)
        bucket = live_dirs if kind == "live" else course_dirs

        if not rec:
            print(f"NOT FOUND [{kind}]: '{donor.title}' → '{expected}'")
            missing.append(donor.title)
            continue

        r_e = rec.entity

        if getattr(e, "broadcast", False):
            bucket.append(_direction(full_id(e), full_id(r_e)))
            print(f"OK (channel) [{kind}]: '{donor.title}' → '{rec.title}'")

        elif getattr(e, "megagroup", False):
            if not getattr(e, "forum", False):
                bucket.append(_direction(f"{full_id(e)}#1", f"{full_id(r_e)}#1"))
                print(f"OK (supergroup) [{kind}]: '{donor.title}' → '{rec.title}'")
                continue

            d_topics = await fetch_all_topics(client, e)
            r_topics = await fetch_all_topics(client, r_e)

            r_by_title = {t.title: t for t in r_topics}
            r_general  = next((t for t in r_topics if t.id == 1), None)

            for d_topic in d_topics:
                if d_topic.id == 1:
                    r_topic = r_general
                else:
                    r_topic = r_by_title.get(d_topic.title)

                if not r_topic:
                    print(f"  Topic '{d_topic.title}' not found at '{rec.title}', skipping")
                    continue

                bucket.append(_direction(
                    f"{full_id(e)}#{d_topic.id}", f"{full_id(r_e)}#{r_topic.id}"
                ))

            print(f"OK (forum) [{kind}]: '{donor.title}' → '{rec.title}'")

    report_unmatched(dialogs)

    # Live — appended to the main config (comments and existing directions kept intact).
    live_backup = write_directions(CONFIG_PATH, live_dirs, merge=True)
    if live_backup:
        print(f"\nLive: appended to {CONFIG_PATH} (backup: {live_backup})")
    else:
        print(f"\nLive: no new directions, {CONFIG_PATH} untouched")

    # Courses — a separate file, read only by past_mode.py.
    if course_dirs:
        courses_backup = write_courses_config(course_dirs)
        note = f" (backup: {courses_backup})" if courses_backup else ""
        print(f"Courses: {len(course_dirs)} direction(s) → {COURSES_CONFIG_PATH}{note}")

    for label, dirs in (("live", live_dirs), ("courses", course_dirs)):
        ch = sum(1 for d in dirs if "#" not in str(d["from"][0]))
        print(f"  {label}: {ch} channel(s) + {len(dirs) - ch} topic(s)")
    if missing:
        print(f"Skipped {len(missing)} donor(s) without a pair: {missing}")


# ── Step 5: Final verification ─────────────────────────────────────────────────

async def step_final_verify(client):
    print("\n=== STEP 5: FINAL VERIFICATION ===\n")
    if not CONFIG_PATH.exists():
        print(f"Config {CONFIG_PATH} not found. Run step 4 first.")
        return

    with open(CONFIG_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    directions   = list(data.get("directions", []))
    if COURSES_CONFIG_PATH.exists():
        with open(COURSES_CONFIG_PATH, encoding="utf-8") as f:
            directions += (yaml.safe_load(f) or {}).get("directions", [])
    entity_cache: dict = {}
    topic_cache:  dict = {}

    async def get_entity(chat_id: int):
        if chat_id not in entity_cache:
            entity_cache[chat_id] = await client.get_entity(chat_id)
            await asyncio.sleep(0.3)
        return entity_cache[chat_id]

    async def get_topics(chat_id: int) -> dict:
        if chat_id not in topic_cache:
            e = await get_entity(chat_id)
            topic_cache[chat_id] = {
                t.id: t for t in await fetch_all_topics(client, e)
            }
        return topic_cache[chat_id]

    channel_dirs = [d for d in directions if "#" not in str(d["from"][0])]
    topic_dirs   = [d for d in directions if "#" in  str(d["from"][0])]
    ok = 0
    fixes = []

    print("--- Channels ---\n")
    for direction in channel_dirs:
        from_id = int(str(direction["from"][0]))
        to_id   = int(str(direction["to"][0]))
        from_e  = await get_entity(from_id)
        if classify_donor(from_e.title or "") == "unknown":
            continue  # a direction from another batch — not our concern
        to_e    = await get_entity(to_id)
        expected = to_citadel(from_e.title)
        if to_e.title == expected:
            print(f"OK: '{from_e.title}' → '{to_e.title}'")
            ok += 1
        elif name_key(to_e.title) == name_key(expected):
            print(f"OK (emoji): '{from_e.title}' → '{to_e.title}'")
            ok += 1
        else:
            print(f"ERROR: '{from_e.title}' → '{to_e.title}' (expected '{expected}')")
            fixes.append(("channel", to_e, expected))

    print("\n--- Topics ---\n")
    for direction in topic_dirs:
        fv = str(direction["from"][0])
        tv = str(direction["to"][0])
        from_id, from_tid = int(fv.split("#")[0]), int(fv.split("#")[1])
        to_id,   to_tid   = int(tv.split("#")[0]),   int(tv.split("#")[1])

        from_e = await get_entity(from_id)
        if classify_donor(from_e.title or "") == "unknown":
            continue  # a direction from another batch — not our concern
        from_topics = await get_topics(from_id)
        to_topics   = await get_topics(to_id)
        f_topic = from_topics.get(from_tid)
        t_topic = to_topics.get(to_tid)

        if not f_topic or not t_topic:
            label = f"#{from_tid} at {from_id}" if not f_topic else f"#{to_tid} at {to_id}"
            print(f"ERROR: topic {label} not found")
            fixes.append(None)
            continue

        if from_tid == 1 and to_tid == 1:
            if f_topic.title == t_topic.title:
                print(f"OK (General): '{f_topic.title}'")
                ok += 1
            else:
                print(f"ERROR (General): '{f_topic.title}' != '{t_topic.title}'")
                fixes.append(("topic", entity_cache[to_id], to_tid, f_topic.title))
        elif f_topic.title == t_topic.title:
            print(f"OK: '{f_topic.title}'")
            ok += 1
        else:
            print(f"ERROR: '{f_topic.title}' != '{t_topic.title}'")
            fixes.append(("topic", entity_cache[to_id], to_tid, f_topic.title))

    real_fixes = [x for x in fixes if x is not None]
    print(f"\n{'All correct' if not fixes else 'Discrepancies found'}: {ok} OK, {len(fixes)} error(s).")

    if not real_fixes:
        return

    print("Fixing discrepancies...")
    for fix in real_fixes:
        if fix[0] == "channel":
            _, e, new_title = fix
            print(f"  Channel → '{new_title}'...")
            await safe_call(client,
                lambda ent=e, t=new_title: client(EditTitleRequest(channel=ent, title=t))
            )
        elif fix[0] == "topic":
            _, e, tid, new_title = fix
            print(f"  Topic #{tid} → '{new_title}'...")
            await safe_call(client,
                lambda ent=e, i=tid, t=new_title: client(
                    EditForumTopicRequest(peer=ent, topic_id=i, title=t)
                )
            )
    print("Done.")


# ── Full cycle ───────────────────────────────────────────────────────────────

async def run_full_cycle(client):
    await step_create_pairs(client)
    await step_configure(client)
    await step_verify(client)
    await step_build_config(client)
    await step_final_verify(client)
    print("\n=== FULL CYCLE COMPLETE ===")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    action = show_menu()

    client = make_client()
    await client.start()

    try:
        dispatch = {
            "full-cycle":   run_full_cycle,
            "create-pairs": step_create_pairs,
            "configure":    step_configure,
            "verify":       step_verify,
            "build-config": step_build_config,
            "final-verify": step_final_verify,
        }
        await dispatch[action](client)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
