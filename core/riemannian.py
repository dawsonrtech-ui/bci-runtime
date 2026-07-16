import numpy as np


def matrix_power(M, p):
    eigenvalues, eigenvectors = np.linalg.eigh(M)
    eigenvalues = np.maximum(eigenvalues, 1e-10)
    return eigenvectors @ np.diag(np.power(eigenvalues, p)) @ eigenvectors.T


def matrix_log(M):
    eigenvalues, eigenvectors = np.linalg.eigh(M)
    eigenvalues = np.maximum(eigenvalues, 1e-10)
    return eigenvectors @ np.diag(np.log(eigenvalues)) @ eigenvectors.T


def matrix_exp(M):
    eigenvalues, eigenvectors = np.linalg.eigh(M)
    return eigenvectors @ np.diag(np.exp(eigenvalues)) @ eigenvectors.T


def project_to_tangent_space(Sigma_t, Sigma_ref):
    Sigma_ref_half = matrix_power(Sigma_ref, 0.5)
    Sigma_ref_inv_half = matrix_power(Sigma_ref, -0.5)
    centered = Sigma_ref_inv_half @ Sigma_t @ Sigma_ref_inv_half
    T_t = Sigma_ref_half @ matrix_log(centered) @ Sigma_ref_half
    return T_t


def vectorize_tangent_space(T_t):
    n = T_t.shape[0]
    dim = n * (n + 1) // 2
    v = np.zeros(dim, dtype=np.float64)
    idx = 0
    for i in range(n):
        for j in range(i, n):
            if i == j:
                v[idx] = T_t[i, j]
            else:
                v[idx] = np.sqrt(2.0) * T_t[i, j]
            idx += 1
    return v


def frechet_mean(covariances, tol=1e-6, max_iter=50):
    S = np.eye(covariances[0].shape[0], dtype=np.float64)
    for _ in range(max_iter):
        S_half_inv = matrix_power(S, -0.5)
        tangent_sum = np.zeros_like(S)
        for P in covariances:
            tangent_sum += matrix_log(S_half_inv @ P @ S_half_inv)
        tangent_sum /= len(covariances)
        step = matrix_power(S, 0.5) @ matrix_exp(tangent_sum) @ matrix_power(S, 0.5)
        diff = np.linalg.norm(step - S) / np.linalg.norm(S)
        S = step
        if diff < tol:
            break
    return S


def geodesic_update(Sigma_ref, Sigma_t, eta, weight=1.0):
    T = project_to_tangent_space(Sigma_t, Sigma_ref)
    scaled_step = eta * weight * T
    Sigma_ref_half = matrix_power(Sigma_ref, 0.5)
    Sigma_ref_inv_half = matrix_power(Sigma_ref, -0.5)
    inner = Sigma_ref_inv_half @ scaled_step @ Sigma_ref_inv_half
    return Sigma_ref_half @ matrix_exp(inner) @ Sigma_ref_half
