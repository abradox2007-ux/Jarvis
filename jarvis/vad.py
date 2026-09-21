import numpy as np
try:
    import onnxruntime as ort
except ImportError:
    ort = None

class SileroVAD:
    """
    Lightweight, torch-free wrapper for Silero Voice Activity Detector (VAD)
    using onnxruntime and numpy.
    """
    def __init__(self, model_path: str):
        if ort is None:
            raise ImportError("onnxruntime is required for SileroVAD but not installed.")
        # Configure onnxruntime session for single-threaded CPU execution (maximum efficiency)
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        
        self.session = ort.InferenceSession(
            model_path,
            sess_options=opts,
            providers=["CPUExecutionProvider"]
        )
        self.reset()
        
    def reset(self):
        """Reset the recurrent state of the VAD network."""
        # Silero VAD expects recurrent state tensor of shape [2, 1, 128]
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        
    def is_speech(self, audio_frame: np.ndarray, threshold: float = 0.5) -> bool:
        """
        Check if the given float32 audio frame contains speech.
        audio_frame: 1D numpy array of normalized float32 values [-1.0, 1.0], length 512.
        """
        prob = self.get_speech_probability(audio_frame)
        return prob >= threshold

    def get_speech_probability(self, audio_frame: np.ndarray) -> float:
        """
        Compute the probability of speech in the given audio frame.
        audio_frame: 1D numpy array of normalized float32 values [-1.0, 1.0], length 512.
        """
        if len(audio_frame) != 512:
            # Fallback if chunk size is incorrect, pad or slice
            if len(audio_frame) < 512:
                frame = np.pad(audio_frame, (0, 512 - len(audio_frame)), 'constant')
            else:
                frame = audio_frame[:512]
        else:
            frame = audio_frame
            
        # Reshape to [1, samples] for batch size 1
        input_data = np.expand_dims(frame, axis=0).astype(np.float32)
        sr_data = np.array(16000, dtype=np.int64)
        
        inputs = {
            "input": input_data,
            "state": self._state,
            "sr": sr_data
        }
        
        # Run ONNX inference
        outputs = self.session.run(None, inputs)
        speech_prob_tensor, new_state = outputs
        
        # Save recurrent state for the next frame
        self._state = new_state
        
        return float(speech_prob_tensor[0, 0])
