"""
Data analysis calculations for HMI Analytics.
Provides statistical analysis, distribution calculations, and correlation analysis.
Adapted from General_Scripts/parse_csv/calculations.py
"""
import numpy as np
from scipy import stats


class DataAnalyzer:
    """Analyzer for graph data with statistical calculations."""
    
    def __init__(self, data, headers):
        """
        Initialize the DataAnalyzer.
        
        Args:
            data: numpy array or list of data (rows x columns)
            headers: list of column names/variable names
        """
        self.data = np.array(data) if not isinstance(data, np.ndarray) else data
        self.headers = list(headers)
        
    def calculate_basic_stats(self, parameter, data_override=None):
        """
        Calculate basic statistics for a given parameter.
        
        Args:
            parameter: variable name to analyze
            data_override: optional array to use instead of looking up parameter
            
        Returns:
            dict with mean, std, rsd, min, max
        """
        if data_override is not None:
            values = np.array(data_override, dtype=float)
        else:
            param_idx = self.headers.index(parameter)
            values = self.data[:, param_idx].astype(float)
        
        # Remove NaN and Inf values
        values = values[~np.isnan(values) & ~np.isinf(values)]
        
        if len(values) == 0:
            return {
                'mean': 0.0,
                'std': 0.0,
                'rsd': 0.0,
                'min': 0.0,
                'max': 0.0,
                'count': 0
            }
        
        return {
            'mean': float(np.mean(values)),
            'std': float(np.std(values)),
            'rsd': self.calculate_rsd(values, self.headers, parameter),
            'min': float(np.min(values)),
            'max': float(np.max(values)),
            'count': len(values)
        }
    
    def calculate_distribution(self, parameter):
        """
        Calculate distribution data for histogram.
        
        Args:
            parameter: variable name to analyze
            
        Returns:
            tuple of (hist, bins)
        """
        param_idx = self.headers.index(parameter)
        values = self.data[:, param_idx].astype(float)
        values = values[~np.isnan(values) & ~np.isinf(values)]
        
        hist, bins = np.histogram(values, bins='auto')
        return hist, bins
    
    def calculate_moving_average(self, parameter, window=5):
        """
        Calculate moving average for a parameter.
        
        Args:
            parameter: variable name
            window: moving average window size
            
        Returns:
            numpy array with moving averages
        """
        param_idx = self.headers.index(parameter)
        values = self.data[:, param_idx].astype(float)
        return np.convolve(values, np.ones(window)/window, mode='valid')
    
    def calculate_correlation(self, param1, param2):
        """
        Calculate Pearson correlation between two parameters.
        
        Args:
            param1: first variable name
            param2: second variable name
            
        Returns:
            correlation coefficient
        """
        idx1 = self.headers.index(param1)
        idx2 = self.headers.index(param2)
        v1 = self.data[:, idx1].astype(float)
        v2 = self.data[:, idx2].astype(float)
        
        # Remove pairs where either is NaN/Inf
        mask = ~(np.isnan(v1) | np.isnan(v2) | np.isinf(v1) | np.isinf(v2))
        v1, v2 = v1[mask], v2[mask]
        
        if len(v1) < 2:
            return 0.0
        return float(stats.pearsonr(v1, v2)[0])

    def calculate_rsd(self, values, headers, param_name):
        """
        Calculate Relative Standard Deviation (%RSD).
        
        For StableWeight with TargetWeight available, uses TargetWeight as denominator.
        Otherwise uses mean.
        """
        if param_name == 'StableWeight' and 'TargetWeight' in headers:
            target_weight_idx = headers.index('TargetWeight')
            target_weight = float(self.data[0][target_weight_idx])
            rsd = (np.std(values) / target_weight) * 100 if target_weight != 0 else 0
        else:
            mean_val = np.mean(values)
            rsd = (np.std(values) / mean_val) * 100 if mean_val != 0 else 0
        return float(rsd)

    def calculate_frequency_distribution(self, param, data_override=None):
        """
        Calculate frequency distribution with intervals, counts, and relative frequencies.
        
        Args:
            param: variable name
            data_override: optional array to use instead
            
        Returns:
            dict with intervals, frequencies, rel_frequencies, bin_edges
        """
        if data_override is not None:
            data = np.array(data_override, dtype=float)
        else:
            param_idx = self.headers.index(param)
            data = self.data[:, param_idx].astype(float)
        
        # Remove NaN/Inf
        data = data[~np.isnan(data) & ~np.isinf(data)]
        
        if len(data) == 0:
            return {
                'intervals': [],
                'frequencies': np.array([]),
                'rel_frequencies': np.array([]),
                'bin_edges': np.array([])
            }
        
        # Calculate optimal bin count (4 to 15 bins based on data size)
        num_bins = min(max(4, len(data) // 10), 15)
        
        frequencies, bin_edges = np.histogram(data, bins=num_bins)
        total_count = np.sum(frequencies)
        rel_freq = (frequencies / total_count) * 100 if total_count > 0 else frequencies * 0
        
        # Format intervals with appropriate decimal places
        intervals = [f"{edge:.2f}" for edge in bin_edges[:-1]]
        
        return {
            'intervals': intervals,
            'frequencies': frequencies,
            'rel_frequencies': rel_freq,
            'bin_edges': bin_edges
        }

    def count_out_of_spec(self, parameter, setpoint, tolerance, data_override=None):
        """
        Count values outside the tolerance range.
        
        Args:
            parameter: variable name
            setpoint: target value
            tolerance: tolerance in percentage
            data_override: optional array to use
            
        Returns:
            tuple of (out_of_spec_count, total_count)
        """
        if data_override is not None:
            values = np.array(data_override, dtype=float)
        else:
            param_idx = self.headers.index(parameter)
            values = self.data[:, param_idx].astype(float)
        
        # Remove NaN/Inf
        values = values[~np.isnan(values) & ~np.isinf(values)]
        
        lower = setpoint * (1 - tolerance / 100)
        upper = setpoint * (1 + tolerance / 100)
        out_of_spec = np.sum((values < lower) | (values > upper))
        total = len(values)
        return int(out_of_spec), int(total)

    def calculate_process_capability(self, setpoint, tolerance, std_dev, mean):
        """
        Calculate process capability indices Cp and Cpk.
        
        Based on: https://www.qualitiso.com/cpk-capacite-fiabilite-process/
        
        Cp = (USL - LSL) / 6σ
        Cpk = min((USL - µ) / 3σ, (µ - LSL) / 3σ)
        
        Where:
            USL = Upper Specification Limit = setpoint * (1 + tolerance/100)
            LSL = Lower Specification Limit = setpoint * (1 - tolerance/100)
            σ = standard deviation
            µ = mean
        
        Args:
            setpoint: target/nominal value
            tolerance: tolerance in percentage (e.g., 1.0 for ±1%)
            std_dev: standard deviation of the data
            mean: mean value of the data
            
        Returns:
            dict with 'cp', 'cpk', 'cp_rating', 'cpk_rating'
        """
        # Calculate specification limits
        usl = setpoint * (1 + tolerance / 100)  # Upper Specification Limit
        lsl = setpoint * (1 - tolerance / 100)  # Lower Specification Limit
        
        # Handle edge cases
        if std_dev == 0 or std_dev is None:
            return {
                'cp': float('inf') if (usl - lsl) > 0 else 0,
                'cpk': float('inf') if (usl - lsl) > 0 else 0,
                'cp_rating': 'N/A (σ=0)',
                'cpk_rating': 'N/A (σ=0)'
            }
        
        # Cp: Process Capability (how much the tolerance covers relative to 6σ)
        # Cp = (USL - LSL) / 6σ
        cp = (usl - lsl) / (6 * std_dev)
        
        # Cpk: Process Capability Index (accounts for centering)
        # Cpk = min((USL - µ) / 3σ, (µ - LSL) / 3σ)
        cpu = (usl - mean) / (3 * std_dev)  # Upper capability
        cpl = (mean - lsl) / (3 * std_dev)  # Lower capability
        cpk = min(cpu, cpl)
        
        # Cpm: Machine Capability Index (very reactive to drift/deregulation)
        # Cpm = Cp / √(1 + 9.(Cp – Cpk)²)
        # Takes into account the off-centering of results
        cp_cpk_diff = cp - cpk
        cpm_denominator = np.sqrt(1 + 9 * (cp_cpk_diff ** 2))
        cpm = cp / cpm_denominator if cpm_denominator != 0 else 0
        
        # Determine ratings based on common thresholds
        def get_rating(value):
            if value >= 1.67:
                return "Excellent"
            elif value >= 1.33:
                return "Capable"
            elif value >= 1.0:
                return "Marginal"
            else:
                return "Not Capable"
        
        return {
            'cp': float(cp),
            'cpk': float(cpk),
            'cpm': float(cpm),
            'cpu': float(cpu),  # Upper capability
            'cpl': float(cpl),  # Lower capability
            'cp_rating': get_rating(cp),
            'cpk_rating': get_rating(cpk),
            'cpm_rating': get_rating(cpm)
        }
