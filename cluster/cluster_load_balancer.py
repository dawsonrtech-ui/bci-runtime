import zmq


def run_edge_load_balancer(client_facing_port=5557, worker_facing_port=5558):
    context = zmq.Context()

    frontend = context.socket(zmq.ROUTER)
    frontend.setsockopt(zmq.RCVHWM, 1000)
    frontend.setsockopt(zmq.SNDHWM, 1000)
    frontend.bind(f"tcp://0.0.0.0:{client_facing_port}")

    backend = context.socket(zmq.DEALER)
    backend.setsockopt(zmq.RCVHWM, 1000)
    backend.setsockopt(zmq.SNDHWM, 1000)
    backend.bind(f"tcp://0.0.0.0:{worker_facing_port}")

    print(f"BCI Edge Proxy Layer initialized. Routing client streams to compute cluster workers.")

    try:
        zmq.proxy(frontend, backend)
    except KeyboardInterrupt:
        pass
    finally:
        frontend.close()
        backend.close()
        context.term()


if __name__ == "__main__":
    run_edge_load_balancer()
