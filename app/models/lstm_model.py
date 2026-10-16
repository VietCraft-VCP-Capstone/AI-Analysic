import numpy as np
from typing import List

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
    
    class LSTMForecaster(nn.Module):
        def __init__(self, input_dim: int = 1, hidden_dim: int = 32, num_layers: int = 1, output_dim: int = 1):
            super(LSTMForecaster, self).__init__()
            self.hidden_dim = hidden_dim
            self.num_layers = num_layers
            self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers, batch_first=True)
            self.linear = nn.Linear(hidden_dim, output_dim)

        def forward(self, x):
            h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_dim).to(x.device)
            c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_dim).to(x.device)
            out, _ = self.lstm(x, (h0, c0))
            out = self.linear(out[:, -1, :])
            return out
except ImportError:
    TORCH_AVAILABLE = False

class LSTMModelService:
    @staticmethod
    def forecast(history_data: List[float], steps_ahead: int = 5) -> List[float]:
        """
        Mock prediction pipeline utilizing a generic LSTM neural network structure.
        """
        if not TORCH_AVAILABLE or len(history_data) < 5:
            last_val = history_data[-1] if history_data else 0.0
            diff = history_data[-1] - history_data[0] if len(history_data) > 1 else 0.0
            trend = diff / len(history_data) if len(history_data) > 1 else 0.0
            return [float(last_val + (i + 1) * trend) for i in range(steps_ahead)]

        try:
            model = LSTMForecaster(input_dim=1, hidden_dim=16, num_layers=1, output_dim=1)
            model.eval()

            seq = np.array(history_data, dtype=np.float32).reshape(-1, 1)
            predictions = []
            current_seq = list(seq[-5:])
            
            with torch.no_grad():
                for _ in range(steps_ahead):
                    input_tensor = torch.tensor([current_seq], dtype=torch.float32)
                    pred = model(input_tensor)
                    pred_val = float(pred.item())
                    predictions.append(pred_val)
                    current_seq.pop(0)
                    current_seq.append([pred_val])

            last_actual = history_data[-1]
            first_pred = predictions[0]
            offset = last_actual - first_pred
            
            adjusted_preds = [float(pred + offset) for pred in predictions]
            return adjusted_preds
            
        except Exception as e:
            last_val = history_data[-1]
            return [float(last_val * (1.02 ** (i + 1))) for i in range(steps_ahead)]
