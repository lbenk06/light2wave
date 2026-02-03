class BaseScene:
    def apply(self, fixtures):
        for fixture in fixtures:
            fixture.set("dimmer", 0.8)
            fixture.set("red", 1.0)
            fixture.set("green", 0.0)
            fixture.set("blue", 0.0)