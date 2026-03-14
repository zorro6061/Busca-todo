import numpy as np


class SpatialEngine:
    """
    Engine for Projective Geometry and Perspective Correction (SLAM-lite).
    Maps image-space detections to 2D floor plan coordinates.
    """

    @staticmethod
    def solve_homography(src_pts, dst_pts):
        """
        Computes the 3x3 Homography matrix H using DLT (Direct Linear Transform).
        src_pts: 4 points in image space [(x1,y1), (x2,y2), (x3,y3), (x4,y4)]
        dst_pts: 4 corresponding points in map space (0-100% or meters)
        """
        A = []
        for i in range(4):
            x, y = src_pts[i][0], src_pts[i][1]
            u, v = dst_pts[i][0], dst_pts[i][1]
            A.append([-x, -y, -1, 0, 0, 0, x * u, y * u, u])
            A.append([0, 0, 0, -x, -y, -1, x * v, y * v, v])

        A = np.asarray(A)
        # Solve A * h = 0 using SVD
        U, S, Vh = np.linalg.svd(A)
        L = Vh[-1, :] / Vh[-1, -1]
        H = L.reshape(3, 3)
        return H

    @staticmethod
    def project_point(H, point):
        """
        Projects a point using the Homography matrix.
        point: (x, y)
        returns: (x', y')
        """
        p = np.array([point[0], point[1], 1])
        projected = np.dot(H, p)
        # Normalize by homogeneous coordinate w
        if projected[2] != 0:
            return (projected[0] / projected[2], projected[1] / projected[2])
        return (projected[0], projected[1])

    @staticmethod
    def get_object_anchor(bbox):
        """
        Calculates the ground anchor point of an object from its BBOX.
        bbox: [ymin, xmin, ymax, xmax] (normalized 0-1000)
        returns: (x, y) point on the floor (bottom-center)
        """
        ymin, xmin, ymax, xmax = bbox
        center_x = (xmin + xmax) / 2
        # Use BOTTOM center as the floor anchor
        return (center_x, ymax)

    @staticmethod
    def create_default_homography():
        """
        Returns an identity matrix or a basic perspective wedge as fallback.
        """
        return np.eye(3).tolist()


def serialize_h(H):
    return H.flatten().tolist()


def deserialize_h(H_list):
    return np.array(H_list).reshape(3, 3)
