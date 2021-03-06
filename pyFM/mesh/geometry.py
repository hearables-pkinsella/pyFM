import numpy as np
import scipy.sparse as sparse


def compute_normals(vertices, faces):
    """
    Compute normals of a triangular mesh

    Parameters
    -----------------------------
    vertices : (n,3) array of vertices coordinates
    faces    : (m,3) array of vertex indices defining faces

    Output
    -----------------------------
    normals : (m,3) array of normalized per-face normals
    """
    v1 = vertices[faces[:, 0]]
    v2 = vertices[faces[:, 1]]
    v3 = vertices[faces[:, 2]]

    normals = np.cross(v2-v1, v3-v1)
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)

    return normals


def compute_faces_areas(vertices, faces):
    """
    Compute per-face areas of a triangular mesh

    Parameters
    -----------------------------
    vertices : (n,3) array of vertices coordinates
    faces    : (m,3) array of vertex indices defining faces

    Output
    -----------------------------
    faces_areas : (m,) array of per-face areas
    """

    v1 = vertices[faces[:,0]]  # (m,3)
    v2 = vertices[faces[:,1]]  # (m,3)
    v3 = vertices[faces[:,2]]  # (m,3)
    faces_areas = 0.5 * np.linalg.norm(np.cross(v2-v1,v3-v1),axis=1)  # (m,)

    return faces_areas


def compute_vertex_areas(vertices, faces, faces_areas=None):
    """
    Compute per-vertex areas of a triangular mesh.
    Area of a vertex, approximated as one third of the sum of the area
    of its adjacent triangles

    Parameters
    -----------------------------
    vertices : (n,3) array of vertices coordinates
    faces    : (m,3) array of vertex indices defining faces

    Output
    -----------------------------
    vert_areas : (n,) array of per-vertex areas
    """
    N = vertices.shape[0]

    if faces_areas is None:
        faces_areas = compute_faces_areas(vertices,faces)  # (m,)

    I = np.concatenate([faces[:,0], faces[:,1], faces[:,2]])
    J = np.zeros_like(I)
    V = np.concatenate([faces_areas, faces_areas, faces_areas])/3

    # Get the (n,) array of vertex areas
    vertex_areas = np.array(sparse.coo_matrix((V, (I, J)), shape=(N, 1)).todense()).flatten()

    return vertex_areas


def grad_f(f, vertices, faces, normals, face_areas=None, use_sym=False):
    """
    Compute the gradient of a function on a mesh

    Parameters
    --------------------------
    f          : (n,) function value on each vertex
    vertices   : (m,3) coordinates of vertices
    faces      : (m,3) indices of vertices for each face
    normals    : (m,3) normals coordinate for each face
    faces_area : (m,) - Optional, array of per-face area, for faster computation
    use_sym    : bool - If true, uses the (slower but) symmetric expression
                 of the gradient

    Output
    --------------------------
    gradient : (m,3) gradient of f on the mesh
    """
    v1 = vertices[faces[:,0]]  # (m,3)
    v2 = vertices[faces[:,1]]  # (m,3)
    v3 = vertices[faces[:,2]]  # (m,3)

    f1 = f[faces[:,0]]  # (m,)
    f2 = f[faces[:,1]]  # (m,)
    f3 = f[faces[:,2]]  # (m,)

    # Compute area for each face
    if face_areas is None:
        face_areas = 0.5 * np.linalg.norm(np.cross(v2-v1,v3-v1),axis=1)  # (m)

    if not use_sym:
        grad2 = np.cross(normals, v1-v3)/(2*face_areas[:,None])  # (n_f,3)
        grad3 = np.cross(normals, v2-v1)/(2*face_areas[:,None])  # (n_f,3)

        gradient = (f2-f1)[:,None] * grad2 + (f3-f1)[:,None] * grad3

    else:
        grad1 = np.cross(normals, v3-v2)/(2*face_areas[:,None])  # (n_f,3)
        grad2 = np.cross(normals, v1-v3)/(2*face_areas[:,None])  # (n_f,3)
        grad3 = np.cross(normals, v2-v1)/(2*face_areas[:,None])  # (n_f,3)

        gradient = f1[:,None] * grad1 + f2[:,None] * grad2 + f3[:,None] * grad3

    return gradient


def get_orientation_op(grad_field, vertices, faces, normals, per_vert_area, rotated=False):
    """
    Compute the orientation operator associated to a gradient field grad(f).

    For a given function g, this operator linearly computes
    < grad(f) x grad(g), n> for each vertex by averaging along the adjacent faces.
    In practice, we compute < n x grad(f), grad(g) > for simpler computation.

    Parameters
    --------------------------------
    grad_field    : (n_f,3) gradient field on the mesh
    vertices      : (n_v,3) coordinates of vertices
    faces         : (n_f,3) indices of vertices for each face
    normals       : (n_f,3) normals coordinate for each face
    per_vert_area : (n_v,) voronoi area for each vertex
    rotated       : bool - whether gradient field is already rotated by n x grad(f)

    Output
    --------------------------
    operator : (n_v,n_v) orientation operator.
    """
    n_vertices = per_vert_area.shape[0]
    per_vert_area = np.asarray(per_vert_area)

    v1 = vertices[faces[:,0]]  # (n_f,3)
    v2 = vertices[faces[:,1]]  # (n_f,3)
    v3 = vertices[faces[:,2]]  # (n_f,3)

    # Define (normalized) gradient directions for each barycentric coordinate on each face
    # Remove normalization since it will disappear after multiplcation
    Jc1 = np.cross(normals,v3-v2)/2
    Jc2 = np.cross(normals,v1-v3)/2
    Jc3 = np.cross(normals,v2-v1)/2

    # Rotate the gradient field
    if rotated:
        rot_field = grad_field
    else:
        rot_field = np.cross(normals,grad_field)  # (n_f,3)

    I = np.concatenate([faces[:,0], faces[:,1], faces[:,2]])
    J = np.concatenate([faces[:,1], faces[:,2], faces[:,0]])

    # Compute pairwise dot products between the gradient directions
    # and the gradient field
    Sij = 1/3*np.concatenate([np.einsum('ij,ij->i', Jc2, rot_field),
                              np.einsum('ij,ij->i', Jc3, rot_field),
                              np.einsum('ij,ij->i', Jc1, rot_field)])

    Sji = 1/3*np.concatenate([np.einsum('ij,ij->i', Jc1, rot_field),
                              np.einsum('ij,ij->i', Jc2, rot_field),
                              np.einsum('ij,ij->i', Jc3, rot_field)])

    In = np.concatenate([I, J, I, J])
    Jn = np.concatenate([J, I, I, J])
    Sn = np.concatenate([Sij, Sji, -Sij, -Sji])

    W = sparse.coo_matrix((Sn, (In, Jn)), shape=(n_vertices, n_vertices)).tocsc()
    inv_area = sparse.diags(1/per_vert_area, shape=(n_vertices, n_vertices), format='csc')

    return inv_area @ W


def geodesic_distmat(vertices, faces):
    """
    Compute geodesic distance matrix using Dijkstra algorithm.
    """
    N = vertices.shape[0]
    edges = edges_from_faces(faces)

    I = edges[:,0]  # (p,)
    J = edges[:,1]  # (p,)
    V = np.linalg.norm(vertices[J] - vertices[I], axis=1)  # (p,)

    In = np.concatenate([I,J])
    Jn = np.concatenate([J,I])
    Vn = np.concatenate([V,V])

    graph = sparse.coo_matrix((Vn, (In, Jn)),shape=(N,N)).tocsr()

    geod_dist = sparse.csgraph.dijkstra(graph)

    return geod_dist


def edges_from_faces(faces):
    """
    Compute all edges in the mesh

    Parameters
    --------------------------------
    faces : (m,3) array defining faces with vertex indices

    Output
    --------------------------
    edges : (p,2) array of all edges defined by vertex indices
            with no particular order
    """
    # Number of verties
    N = 1 + np.max(faces)

    # Use a sparse matrix and find non-zero elements
    I = np.concatenate([faces[:,0], faces[:,1], faces[:,2]])
    J = np.concatenate([faces[:,1], faces[:,2], faces[:,0]])
    V = np.ones_like(I)
    M = sparse.coo_matrix((V, (I, J)), shape=(N, N))

    inds1,inds2 = M.nonzero()  # (p,), (p,)
    edges = np.hstack([inds1[:,None], inds2[:,None]])

    return edges


def farthest_point_sampling(D, k, random_init=True):
    """
    Samples points using farthest point sampling

    Parameters
    -------------------------
    D           : (n,n) distance matrix between points
    k           : int - number of points to sample
    random_init : Whether to sample the first point randomly or to
                  take the furthest away from all the other ones

    Output
    --------------------------
    fps : (k,) array of indices of sampled points
    """
    if random_init:
        inds = [np.random.randint(D.shape[0])]
    else:
        inds = [np.argmax(D.sum(1))]

    dists = D[inds]

    for _ in range(k-1):
        newid = np.argmax(dists)
        inds.append(newid)
        dists = np.minimum(dists,D[newid])

    return np.asarray(inds)
