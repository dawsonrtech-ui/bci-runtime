import numpy as np


class MultiHeadSelfAttentionNumPy:
    def __init__(self, d_model=32, n_heads=2):
        self.d_model = d_model
        self.n_heads = n_heads
        self.d_k = d_model // n_heads
        assert self.d_k * n_heads == d_model, "d_model must be divisible by n_heads"
        scale = np.sqrt(2.0 / d_model)
        self.W_q = np.random.randn(d_model, d_model) * scale
        self.W_k = np.random.randn(d_model, d_model) * scale
        self.W_v = np.random.randn(d_model, d_model) * scale
        self.W_o = np.random.randn(d_model, d_model) * scale

    def _softmax(self, x, axis=-1):
        e_x = np.exp(x - np.max(x, axis=axis, keepdims=True))
        return e_x / np.sum(e_x, axis=axis, keepdims=True)

    def forward(self, X):
        seq_len, _ = X.shape
        Q = (X @ self.W_q).reshape(seq_len, self.n_heads, self.d_k).transpose(1, 0, 2)
        K = (X @ self.W_k).reshape(seq_len, self.n_heads, self.d_k).transpose(1, 0, 2)
        V = (X @ self.W_v).reshape(seq_len, self.n_heads, self.d_k).transpose(1, 0, 2)
        scores = (Q @ K.transpose(0, 2, 1)) / np.sqrt(self.d_k)
        weights = self._softmax(scores, axis=-1)
        context = weights @ V
        concat = context.transpose(1, 0, 2).reshape(seq_len, self.d_model)
        return concat @ self.W_o


def softmax(x, axis=-1):
    x_max = np.max(x, axis=axis, keepdims=True)
    e_x = np.exp(x - x_max)
    return e_x / np.sum(e_x, axis=axis, keepdims=True)


def layer_norm(x, gamma, beta, eps=1e-6):
    mean = np.mean(x, axis=-1, keepdims=True)
    var = np.var(x, axis=-1, keepdims=True)
    return gamma * (x - mean) / np.sqrt(var + eps) + beta


class AttentionHead:
    def __init__(self, d_model, d_head):
        scale = 1.0 / np.sqrt(d_model)
        self.W_q = np.random.uniform(-scale, scale, (d_model, d_head)).astype(np.float64)
        self.W_k = np.random.uniform(-scale, scale, (d_model, d_head)).astype(np.float64)
        self.W_v = np.random.uniform(-scale, scale, (d_model, d_head)).astype(np.float64)
        self.W_o = np.random.uniform(-scale, scale, (d_head, d_model)).astype(np.float64)
        self.d_head = d_head

    def __call__(self, Q, K, V, mask=None):
        q = Q @ self.W_q
        k = K @ self.W_k
        v = V @ self.W_v
        scores = q @ k.T / np.sqrt(self.d_head)
        if mask is not None:
            scores = scores + mask
        attn = softmax(scores, axis=-1)
        return attn @ v @ self.W_o


class TransformerBlock:
    def __init__(self, d_model, n_heads, d_ff):
        scale = 1.0 / np.sqrt(d_model)
        self.heads = [AttentionHead(d_model, d_model // n_heads) for _ in range(n_heads)]
        self.W_1 = np.random.uniform(-scale, scale, (d_model, d_ff)).astype(np.float64)
        self.b_1 = np.zeros(d_ff, dtype=np.float64)
        self.W_2 = np.random.uniform(-scale, scale, (d_ff, d_model)).astype(np.float64)
        self.b_2 = np.zeros(d_model, dtype=np.float64)
        self.ln1_g = np.ones(d_model, dtype=np.float64)
        self.ln1_b = np.zeros(d_model, dtype=np.float64)
        self.ln2_g = np.ones(d_model, dtype=np.float64)
        self.ln2_b = np.zeros(d_model, dtype=np.float64)

    def __call__(self, x, mask=None):
        attn_out = np.zeros_like(x)
        for h in self.heads:
            attn_out += h(x, x, x, mask)
        attn_out = attn_out / len(self.heads)
        x = layer_norm(x + attn_out, self.ln1_g, self.ln1_b)
        ff = np.maximum(x @ self.W_1 + self.b_1, 0)
        x = layer_norm(x + ff @ self.W_2 + self.b_2, self.ln2_g, self.ln2_b)
        return x


class CECT:
    def __init__(self, n_commands=8, d_model=32, n_heads=2, n_layers=2, d_ff=64, max_seq=16):
        self.n_commands = n_commands
        self.d_model = d_model
        self.max_seq = max_seq
        scale = 1.0 / np.sqrt(d_model)
        self.command_embed = np.random.uniform(-scale, scale, (n_commands, d_model)).astype(np.float64)
        self.pos_embed = np.random.uniform(-scale, scale, (max_seq, d_model)).astype(np.float64)
        self.conf_proj = np.random.uniform(-scale, scale, (1, d_model)).astype(np.float64)
        self.state_proj = np.random.uniform(-scale, scale, (1, d_model)).astype(np.float64)
        self.blocks = [TransformerBlock(d_model, n_heads, d_ff) for _ in range(n_layers)]
        self.out_proj = np.random.uniform(-scale, scale, (d_model, n_commands)).astype(np.float64)
        self.out_bias = np.zeros(n_commands, dtype=np.float64)

    def embed(self, commands, confidences, game_state):
        seq_len = len(commands)
        cmd_emb = self.command_embed[commands]
        conf_emb = np.outer(confidences.flatten(), self.conf_proj.flatten())
        x = cmd_emb + conf_emb
        x += self.pos_embed[:seq_len]
        return x

    def forward(self, commands, confidences, game_state=None):
        x = self.embed(commands, confidences, game_state)
        mask = None
        for block in self.blocks:
            x = block(x, mask)
        logits = x[-1] @ self.out_proj + self.out_bias
        return softmax(logits)

    def correct(self, commands, confidences, game_state=None):
        probs = self.forward(commands, confidences, game_state)
        corrected = int(np.argmax(probs))
        return corrected, probs[corrected]

    def train_step(self, batch_commands, batch_confidences, batch_targets, lr=0.01):
        total_loss = 0.0
        for commands, confidences, target in zip(batch_commands, batch_confidences, batch_targets):
            probs = self.forward(commands, confidences)
            loss = -np.log(probs[target] + 1e-10)
            total_loss += loss
            d_logits = probs.copy()
            d_logits[target] -= 1.0
            last_emb = self.embed(commands[-1:], confidences[-1:], None)[0]
            self.out_proj -= lr * np.outer(last_emb, d_logits)
            self.out_bias -= lr * d_logits
        return total_loss / len(batch_commands)

    def generate_synthetic_data(self, n_sequences=500, seq_len=8, seed=47):
        rng = np.random.default_rng(seed)
        confusion = np.eye(self.n_commands) * 0.8
        confusion += (1.0 - confusion.sum(axis=1, keepdims=True)) / self.n_commands
        data = []
        for _ in range(n_sequences):
            true_cmd = rng.integers(0, self.n_commands)
            commands = rng.integers(0, self.n_commands, seq_len)
            commands[-1] = rng.choice(self.n_commands, p=confusion[true_cmd])
            confidences = rng.uniform(0.4, 0.95, seq_len)
            data.append((commands, confidences, true_cmd))
        return data

    def train_on_synthetic(self, n_epochs=10, sequences_per_epoch=200, lr=0.01, seq_len=8):
        losses = []
        for epoch in range(n_epochs):
            data = self.generate_synthetic_data(sequences_per_epoch, seq_len)
            batch_cmds = [d[0] for d in data]
            batch_confs = [d[1] for d in data]
            batch_targets = [d[2] for d in data]
            loss = self.train_step(batch_cmds, batch_confs, batch_targets, lr)
            losses.append(float(loss))
        return losses


class CECTTransformerIntegration:
    def __init__(self, d_tangent=36, d_context=4, d_model=32, n_actions=4):
        self.d_model = d_model
        self.n_actions = n_actions
        scale = 0.1
        self.W_tangent_proj = np.random.randn(d_tangent, d_model) * scale
        self.W_context_proj = np.random.randn(d_context, d_model) * scale
        self.W_output_classifier = np.random.randn(d_model, n_actions) * scale
        self.W_ern_head = np.random.randn(d_model, 1) * scale

    def forward(self, v_t, current_game_context):
        token_neural = v_t @ self.W_tangent_proj
        token_context = current_game_context @ self.W_context_proj
        sequence_block = np.vstack([token_neural, token_context])
        aggregated = np.mean(sequence_block, axis=0)
        logits = aggregated @ self.W_output_classifier
        probs = softmax(logits)
        action_intent = int(np.argmax(probs))
        confidence = float(probs[action_intent])
        logit_ern = aggregated @ self.W_ern_head
        p_error = float(1.0 / (1.0 + np.exp(-logit_ern[0])))
        return action_intent, confidence, p_error
