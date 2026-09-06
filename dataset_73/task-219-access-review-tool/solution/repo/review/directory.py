"""Groups, users and what a user actually belongs to (spec sections 1, 2)."""
from collections import deque


class Directory:
    def __init__(self):
        self.groups = {}
        self.group_names = []
        self.users = []
        self.user_by_name = {}

    def add_group(self, record):
        self.groups[record["name"]] = record
        self.group_names.append(record["name"])

    def add_user(self, record):
        self.users.append(record)
        self.user_by_name[record["name"]] = record

    def looping_groups(self):
        """1.5 every group that can reach itself, in the order defined."""
        looping = []
        for start in self.group_names:
            if self._reaches(start, start):
                looping.append(start)
        return looping

    def _reaches(self, start, target):
        seen = set()
        queue = deque([start])
        while queue:
            for member in self.groups.get(queue.popleft(), {}).get("members") or []:
                if member == target:
                    return True
                if member in seen or member not in self.groups:
                    continue
                seen.add(member)
                queue.append(member)
        return False

    def membership(self, user, on_missing):
        """2.2 breadth first from the user's own list, each group once."""
        found = []
        seen = set()
        queue = deque(user.get("groups") or [])
        while queue:
            name = queue.popleft()
            if name in seen:
                continue
            seen.add(name)
            group = self.groups.get(name)
            if group is None:
                on_missing(name)                                   # 1.4
                continue
            found.append(group)
            queue.extend(group.get("members") or [])
        return found
