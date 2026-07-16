import numpy as np

try:
    from brainflow.board_shim import BoardShim, BrainFlowInputParams
    from brainflow.board_ids import BoardIds
    _HAS_BRAINFLOW = True
except ImportError:
    _HAS_BRAINFLOW = False
    BoardIds = None


class OpenBCIBoard:
    def __init__(self, port=None, board_type="cyton", sfreq=250):
        self._port = port
        self._board_type = board_type
        self._sfreq = sfreq
        self._n_channels = 8 if board_type == "cyton" else 16
        self._running = False
        self._board_shim = None
        self._sim = None

    def start(self):
        if _HAS_BRAINFLOW:
            self._start_brainflow()
        else:
            from board.base import SimulatedBoard
            self._sim = SimulatedBoard(self._n_channels, self._sfreq)
            self._sim.start()
            self._running = True

    def _start_brainflow(self):
        params = BrainFlowInputParams()
        if self._port:
            params.serial_port = self._port
        board_id = BoardIds.CYTON_BOARD if self._board_type == "cyton" else BoardIds.CYTON_DAISY_BOARD
        self._board_shim = BoardShim(board_id, params)
        self._board_shim.prepare_session()
        self._board_shim.start_stream(45000)
        self._running = True

    def read(self, n_samples=1):
        if not self._running:
            raise RuntimeError("Board not started")
        if self._board_shim is not None:
            data = self._board_shim.get_board_data(n_samples)
            if data.shape[1] < n_samples:
                return np.zeros((self._n_channels, n_samples))
            eeg_channels = BoardShim.get_eeg_channels(self._board_shim.get_board_id())
            return data[eeg_channels, :]
        return self._sim.read(n_samples)

    def stop(self):
        if self._board_shim is not None:
            try:
                self._board_shim.stop_stream()
                self._board_shim.release_session()
            except Exception:
                pass
        elif hasattr(self, '_sim'):
            self._sim.stop()
        self._running = False

    @property
    def n_channels(self):
        return self._n_channels

    @property
    def sfreq(self):
        return self._sfreq

    @property
    def channel_names(self):
        return [f"CH{i+1}" for i in range(self._n_channels)]
