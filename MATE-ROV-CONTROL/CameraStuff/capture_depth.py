import pyzed.sl as sl

def main():
    init = sl.InitParameters(depth_mode=sl.DEPTH_MODE.NEURAL,
                             coordinate_units=sl.UNIT.MILLIMETER,
                             coordinate_system=sl.COORDINATE_SYSTEM.RIGHT_HANDED_Y_UP)
    init.camera_resolution = sl.RESOLUTION.HD720

    zed = sl.Camera()
    if zed.open(init) != sl.ERROR_CODE.SUCCESS:
        print("Failed to open ZED camera")
        exit()

    runtime = sl.RuntimeParameters()
    point_cloud = sl.Mat()

    if zed.grab(runtime) == sl.ERROR_CODE.SUCCESS:
        zed.retrieve_measure(point_cloud, sl.MEASURE.XYZRGBA, sl.MEM.CPU)
        err = point_cloud.write("Pointcloud.ply")
        if err == sl.ERROR_CODE.SUCCESS:
            print("Saved Pointcloud.ply")
        else:
            print("Failed to save point cloud:", err)

    zed.close()

if __name__ == "__main__":
    main()
