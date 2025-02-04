class Pose():
    """
    Place holder code for now: rotation can be rotation matrix, quaternion, or euler angles. euler angles suffer from gimble lock and discontinuity, 
    so i think we should use quaternions (im more familiar with them)
    """
    def __init__(self,position, rotation):
        self.position = position
        self.rotation = rotation 

    #TODO: add overides for addition, subtraction,
    #TODO: add functions for rotation
    #TODO: add functions for coordiate system conversion (local to global, other local references, etc)