import asyncio
import json
import numpy as np
import zmq
import zmq.asyncio


class BCIArbitrationServer:
    def __init__(self, host="127.0.0.1", port=5556):
        self.host = host
        self.port = port
        self.context = zmq.asyncio.Context()
        self.socket = self.context.socket(zmq.ROUTER)
        self.socket.set_hwm(100)
        self.active_user_pipelines = {}
        self.is_running = False

    def register_pipeline(self, user_id, orchestrator_instance):
        self.active_user_pipelines[user_id] = orchestrator_instance
        print(f"User registered to Arbitration Layer: {user_id}")

    async def start_server_loop(self):
        self.socket.bind(f"tcp://{self.host}:{self.port}")
        self.is_running = True
        print(f"Multi-User Arbitration Server listening on tcp://{self.host}:{self.port}")

        try:
            while self.is_running:
                multipart_msg = await self.socket.recv_multipart()
                identity, _, payload_bytes = multipart_msg

                try:
                    payload = json.loads(payload_bytes.decode('utf-8'))
                    user_id = payload.get("user_id")

                    if not user_id or user_id not in self.active_user_pipelines:
                        continue

                    x_raw = np.array(payload["raw_channels"], dtype=np.float64)
                    game_context = np.array(payload["game_context"], dtype=np.float64)

                    pipeline = self.active_user_pipelines[user_id]
                    action_id, confidence, p_err = pipeline.step(x_raw, game_context)

                    response = {
                        "user_id": user_id,
                        "sample_id": payload.get("sample_id", 0),
                        "action_id": action_id,
                        "confidence": confidence,
                        "p_error": p_err,
                    }

                    await self.socket.send_multipart([
                        identity,
                        b"",
                        json.dumps(response).encode('utf-8'),
                    ])

                except Exception as parse_error:
                    print(f"Drop frame error on socket route parsing: {parse_error}")

        except asyncio.CancelledError:
            pass
        finally:
            self.socket.close()
            self.context.term()
            print("Arbitration server context torn down cleanly.")

    def stop(self):
        self.is_running = False
