"""The skill catalogue: what skills exist, how people write them, and how they relate.

It is loaded from data/skills.json, so adding a skill means editing a data file, not code.

Three kinds of knowledge live here:
  * aliases   - "JS", "Java Script" and "ECMAScript" are all JavaScript.
  * implies   - knowing Django means knowing Python; knowing PostgreSQL means knowing SQL.
  * groups    - skills in the same family (Kafka and RabbitMQ are both message queues).
"""
import json
import re
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "skills.json"

# Filler words people put around a skill: "Strong Python skills", "experience with Docker"
_PREFIX = re.compile(r"^(?:strong|solid|good|excellent|proficient|proficiency in|experience with|experience in|"
                     r"knowledge of|understanding of|hands-on experience with|familiarity with|working knowledge of|expertise in)\s+")
_SUFFIX = re.compile(r"\s+(?:skills?|experience|knowledge|development|programming|framework|library)$")


def normalise(text: str) -> str:
    """'  Node.JS  ' -> 'node.js'. Lowercase, single spaces, no edge punctuation."""
    text = re.sub(r"\s+", " ", str(text).strip().lower())
    return text.strip(" .,:;()[]\"'")


class SkillCatalog:
    def __init__(self, data: dict):
        self.version = data["version"]
        self._skills: dict[str, dict] = {}
        self._lookup: dict[str, str] = {}      # every way of writing a skill -> its id
        scan_aliases: dict[str, str] = {}      # aliases safe to look for inside sentences -> id

        for kind, items in (("technical", data["skills"]), ("soft", data["soft_skills"])):
            for item in items:
                if item["id"] in self._skills:
                    raise ValueError(f"duplicate skill id: {item['id']}")
                self._skills[item["id"]] = {**item, "kind": kind}
                names = [item["id"], item["name"], *item.get("aliases", []), *item.get("lookup_only", [])]
                for name in names:
                    key = normalise(name)
                    if self._lookup.get(key, item["id"]) != item["id"]:
                        raise ValueError(f"alias '{key}' belongs to two skills")
                    self._lookup[key] = item["id"]
                # Only technical skills are searched for inside sentences, and only the safe spellings
                if kind == "technical" and item.get("text_scan", True):
                    for name in [item["name"], *item.get("aliases", [])]:
                        scan_aliases[normalise(name)] = item["id"]

        for skill in self._skills.values():
            for target in skill.get("implies", []):
                if target not in self._skills:
                    raise ValueError(f"{skill['id']} implies unknown skill {target}")

        self._groups: dict[str, set[str]] = {}
        for group, members in data.get("groups", {}).items():
            for member in members:
                self._groups.setdefault(member, set()).add(group)

        # Soft skills can be spotted too, but only by their proper name or a multi-word phrase
        # ("communication skills", "team player"). Single-word aliases such as "initiative" are too vague.
        soft_scan: dict[str, str] = {}
        for item in data["soft_skills"]:
            for name in [item["name"], *item.get("aliases", [])]:
                if " " in name or name == item["name"]:
                    soft_scan[normalise(name)] = item["id"]
        self._soft_ids = soft_scan
        self._soft_regex = re.compile(
            r"(?<![\w+#.])(?:" + "|".join(re.escape(n) for n in sorted(soft_scan, key=len, reverse=True)) + r")(?![\w+#])"
        ) if soft_scan else None

        self._scan_ids = scan_aliases
        names = sorted(scan_aliases, key=len, reverse=True)   # longest first: "java script" before "java"
        self._scan_regex = re.compile(
            r"(?<![\w+#.])(?:" + "|".join(re.escape(n) for n in names) + r")(?![\w+#])"
        ) if names else None

    # ---------- looking skills up ----------
    def lookup(self, name: str) -> str | None:
        """Return the skill id for any spelling, or None for a skill we do not know."""
        key = normalise(name)
        candidates = [key]
        stripped = _SUFFIX.sub("", _PREFIX.sub("", key))
        if stripped != key:
            candidates.append(stripped)
        for candidate in candidates:
            if candidate in self._lookup:
                return self._lookup[candidate]
        return None

    def name_of(self, skill_id: str) -> str:
        return self._skills[skill_id]["name"] if skill_id in self._skills else skill_id

    def kind_of(self, skill_id: str) -> str:
        return self._skills[skill_id]["kind"] if skill_id in self._skills else "technical"

    def find_in_text(self, text: str) -> set[str]:
        """Which known technical skills are written inside this sentence or paragraph."""
        if not self._scan_regex:
            return set()
        return {self._scan_ids[normalise(m.group(0))] for m in self._scan_regex.finditer(text.lower())
                if normalise(m.group(0)) in self._scan_ids}

    def find_soft_in_text(self, text: str) -> set[str]:
        """Which soft skills are named in this text (by name or a clear phrase)."""
        if not self._soft_regex:
            return set()
        return {self._soft_ids[normalise(m.group(0))] for m in self._soft_regex.finditer(text.lower())
                if normalise(m.group(0)) in self._soft_ids}

    # ---------- relations ----------
    def implied(self, skill_id: str) -> set[str]:
        """Everything that knowing this skill also means (Django -> Python). Not including itself."""
        found: set[str] = set()
        stack = list(self._skills.get(skill_id, {}).get("implies", []))
        while stack:
            current = stack.pop()
            if current not in found:
                found.add(current)
                stack.extend(self._skills[current].get("implies", []))
        return found

    def specifics(self, skill_id: str) -> set[str]:
        """Skills whose knowledge includes this one (SQL <- PostgreSQL, MySQL)."""
        return {other for other in self._skills if skill_id in self.implied(other)}

    def shared_family(self, a: str, b: str) -> str | None:
        common = self._groups.get(a, set()) & self._groups.get(b, set())
        return sorted(common)[0] if common else None


@lru_cache(maxsize=1)
def get_catalog() -> SkillCatalog:
    return SkillCatalog(json.loads(DATA_FILE.read_text(encoding="utf-8")))
