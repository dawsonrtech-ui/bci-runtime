import os
import time
import zmq
import numpy as np
from core.orchestrator import BCIEngineOrchestrator
from core.secure_gateway import SecureBCIGateway


def run_compute_worker_node(balancer_address="tcp://127.0.0.1:5558",
                            shared_key=None):
    if shared_key is None:
        shared_key = os.environ.get("BCI_SHARED_KEY", "")
    context = zmq.Context()
    socket = context.socket(zmq.DEALER)
    socket.setsockopt(zmq.RCVHWM, 100)
    socket.setsockopt(zmq.SNDHWM, 100)
    socket.connect(balancer_address)

    crypto = SecureBCIGateway(shared_key)
    local_user_pipelines = {}
    print("Compute Worker Node online and listening for balanced traffic frames...")

    while True:
        message_parts = socket.recv_multipart()
        client_identity = message_parts[0]
        encrypted_payload = message_parts[2]

        try:
            payload = crypto.decrypt_payload(encrypted_payload)
            user_id = payload["user_id"]

            if user_id not in local_user_pipelines:
                local_user_pipelines[user_id] = BCIEngineOrchestrator(initialize_lazy=True)

            x_raw = np.array(payload["raw_channels"], dtype=np.float64)
            context_vector = np.array(payload["game_context"], dtype=np.float64)

            action_id, conf, p_err = local_user_pipelines[user_id].step(x_raw, context_vector)

            response_data = {
                "user_id": user_id,
                "action_id": action_id,
                "confidence": conf,
                "p_error": p_err,
            }

            encrypted_response = crypto.encrypt_payload(response_data)
            socket.send_multipart([client_identity, b"", encrypted_response])

        except Exception:
            continue


if __name__ == "__main__":
    run_compute_worker_node()
