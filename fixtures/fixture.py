class Fixture:

    #fixture id: name vom gerät, profile: welche kanäle und was macht jeder (dictionary mit den kanal definitionen), adress: startadresse
    def __init__(self, fixture_id, profile, address, x=0, y=0, traverse=None, snap_point=None):  
        self.id=fixture_id
        self.profile=profile
        self.profile_id=profile.get("profile_id","unknown")
        self.address=address
        self.x=x
        self.y=y
        self.traverse=traverse
        self.snap_point=snap_point


        self.values={}
        for channel in profile["channels"]:
            role=channel["role"]
            if role != "unused":
                self.values[role]=0.0

        # Laser: Modus-Kanal auf "Statisch DMX" vorsetzen (Wert 175/255 ≈ 0.686)
        # Ohne das ignoriert der Laser alle DMX-Befehle (Wert < 150 = Laser aus)
        if "laser_mode" in self.values:
            self.values["laser_mode"] = 175 / 255.0
    
    def set(self, role, value):
        if role in self.values:
            self.values[role] = max(0.0, min(1.0, value))
    
    def get(self, role):
        return self.values.get(role, 0.0)
    
    def has(self, role):
        return role in self.values
    @property
    def roles(self):
        return self.values.keys()
    
    #werte zwischen 0 und 255 ins universe schreiben
    def render(self, universe):
        base=self.address-1
        for i, ch in enumerate(self.profile["channels"]):
            role=ch["role"]
            universe[base+i]=int(self.values.get(role, 0.0)*255)
        
    #gibt aktuelle farbe für livebild als rgb-tupel zurück (wenn weiss vorhanden ist wird es addiert)
    def get_color(self):
        
        dim=self.values.get("dimmer",1.0)
        r=int(self.values.get("red",0.0)*dim*255)
        g=int(self.values.get("green",0.0)*dim*255)
        b=int(self.values.get("blue",0.0)*dim*255)

        if self.has("white"):
            w=int(self.values.get("white",0.0)*dim*255)
            r=min(255, r+w)
            g=min(255, g+w)
            b=min(255, b+w)
        
        return (r,g,b)
    

    def set_color(self, r, g, b):
        #umrechnung von 0-255 auf 0.0-1.0
        self.set("red",r/255.0)
        self.set("green",g/255.0)
        self.set("blue",b/255.0)

        if self.has("dimmer"):
            self.set("dimmer", 1.0)
