class Universe:
    
    def __init__(self):
        self.channels=[0]*512 

    def clear(self):
        for i in range(512):
            self.channels[i]=0