import os
import numpy as np


class BCIProfileManager:
    @staticmethod
    def save_user_profile(filepath, user_id, csp_matrix, sigma_ref):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        np.savez_compressed(
            filepath,
            user_id=user_id,
            csp_weights=csp_matrix,
            sigma_reference=sigma_ref,
            timestamp=np.datetime64('now'),
        )
        print(f"Profile [{user_id}] saved to {filepath}")

    @staticmethod
    def load_user_profile(filepath):
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"No profile at {filepath}")
        with np.load(filepath, allow_pickle=True) as data:
            user_id = str(data['user_id'])
            csp_weights = data['csp_weights']
            sigma_reference = data['sigma_reference']
        print(f"Profile loaded for user: {user_id}")
        return csp_weights, sigma_reference
