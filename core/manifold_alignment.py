import numpy as np
import scipy.linalg
from core.riemannian import matrix_power, matrix_log


class ProcrustesManifoldAligner:
    def __init__(self, low_dim_channels=8):
        self.n = low_dim_channels
        self.R = np.eye(self.n)
        self.scale = 1.0

    def compute_alignment_transform(self, X_saved_anchor, X_new_anchor):
        Ref_Origin = np.eye(self.n)

        def flatten_to_tangent(matrices):
            vectors = []
            cov_half = matrix_power(Ref_Origin, 0.5)
            cov_inv_half = matrix_power(Ref_Origin, -0.5)
            for M in matrices:
                T = cov_half @ matrix_log(cov_inv_half @ M @ cov_inv_half) @ cov_half
                idx = np.triu_indices(self.n)
                vectors.append(T[idx])
            return np.array(vectors)

        Y_saved = flatten_to_tangent(X_saved_anchor)
        Y_new = flatten_to_tangent(X_new_anchor)

        mu_saved = np.mean(Y_saved, axis=0)
        mu_new = np.mean(Y_new, axis=0)
        Y_saved_centered = Y_saved - mu_saved
        Y_new_centered = Y_new - mu_new

        M_cross = Y_saved_centered.T @ Y_new_centered
        U, s, Vt = scipy.linalg.svd(M_cross)

        self.R = U @ Vt
        self.scale = np.sum(s) / (np.sum(Y_new_centered ** 2) + 1e-10)
        print(f"Manifold alignment: scale={self.scale:.4f}")

    def align_incoming_matrix(self, Sigma_t):
        idx = np.triu_indices(self.n)
        Ref_Origin = np.eye(self.n)
        cov_half = matrix_power(Ref_Origin, 0.5)
        cov_inv_half = matrix_power(Ref_Origin, -0.5)
        T_raw = cov_half @ matrix_log(cov_inv_half @ Sigma_t @ cov_inv_half) @ cov_half
        v_raw = T_raw[idx]
        v_aligned = self.scale * (v_raw @ self.R)
        T_aligned = np.zeros_like(Sigma_t)
        T_aligned[idx] = v_aligned
        T_aligned = T_aligned + T_aligned.T - np.diag(np.diag(T_aligned))
        Sigma_aligned = cov_half @ scipy.linalg.expm(
            cov_inv_half @ T_aligned @ cov_inv_half
        ) @ cov_half
        return Sigma_aligned
