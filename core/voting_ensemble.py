import numpy as np


class TemporalVotingEnsemble:
    def __init__(self, window_size=12, confidence_threshold=0.75, entropy_floor=0.4):
        self.window_size = window_size
        self.min_confidence = confidence_threshold
        self.entropy_floor = entropy_floor
        self.history = []

    def _calculate_shannon_entropy(self, probabilities):
        probs = np.clip(probabilities, 1e-12, 1.0)
        return -np.sum(probs * np.log2(probs))

    def evaluate_intent(self, raw_action_id, model_probabilities):
        self.history.append(raw_action_id)
        if len(self.history) > self.window_size:
            self.history.pop(0)

        if len(self.history) < self.window_size:
            return 0, False

        entropy = self._calculate_shannon_entropy(model_probabilities)
        if entropy > (self.entropy_floor * np.log2(len(model_probabilities))):
            return 0, False

        counts = np.bincount(self.history)
        majority_action = np.argmax(counts)
        vote_ratio = counts[majority_action] / self.window_size

        if vote_ratio >= self.min_confidence:
            return int(majority_action), True

        return 0, False

    def reset(self):
        self.history = []
