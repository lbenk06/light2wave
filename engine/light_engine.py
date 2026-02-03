from engine.universe import Universe


class LightEngine:
    def __init__(self):
        self.universe=Universe()
        self.fixtures=[]

    def add_fixture(self, fixture):
        self.fixtures.append(fixture)

    def render(self):
        self.universe.clear()
        for fixture in self.fixtures:
            fixture.render(self.universe.channels)
        return self.universe.channels