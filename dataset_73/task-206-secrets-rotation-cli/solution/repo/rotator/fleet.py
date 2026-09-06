"""Consumers, environments and their health (spec section 2)."""


class Fleet:
    def __init__(self, environments):
        self._order = list(environments)                  # 2.1 rollout order
        self._health = {env: True for env in self._order}  # 2.4 healthy to begin
        self._consumers = {}

    @property
    def order(self):
        return self._order

    def knows(self, env):
        return env in self._health

    def register(self, consumer_id, env):
        # 2.2 re-registering moves the consumer and keeps its acknowledgements
        self._consumers[consumer_id] = env

    def has_consumer(self, consumer_id):
        return consumer_id in self._consumers

    def members_of(self, env):
        return [cid for cid, home in self._consumers.items() if home == env]

    def set_health(self, env, ok):
        self._health[env] = ok

    def is_healthy(self, env):
        return self._health[env]
