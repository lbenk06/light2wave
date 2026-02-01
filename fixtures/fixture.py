class Fixture:

    #fixture id: name vom gerät, profile: welche kanäle und was macht jeder (dictionary mit den kanal definitionen), adress: startadresse
    def __init__(self, fixture_id, profile, adress):  
        self.id=fixture_id
        self.profile=profile
        self.adress=adress
        self.values={ch["role"]: 0.0 for ch in profile["channels"]}

    
    def set(self, role, value):
        if role in self.values:
            self.values[role] = max(0.0, min(1.0, value))
    
    def get(self, role):
        return self.values.get(role, 0.0)
    
    #werte zwischen 0 und 255 ins universe schreiben
    def render(self, universe):
        base=self.adress-1
        for i, ch in enumerate(self.profile["channels"]):
            role=ch["role"]
            universe[base+i]=int(self.values.get(role, 0.0)*255)
        