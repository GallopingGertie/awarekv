import json
import csv
from typing import List, Dict
from dakv.logging import get_logger


logger = get_logger()


class MetricsExporter:
    @staticmethod
    def export_to_json(metrics: List[Dict], filepath: str):
        try:
            with open(filepath, 'w') as f:
                json.dump(metrics, f, indent=2)
            logger.info(f"Exported {len(metrics)} metrics to {filepath}")
        except Exception as e:
            logger.error(f"Failed to export metrics to JSON: {e}")
    
    @staticmethod
    def export_to_csv(metrics: List[Dict], filepath: str):
        try:
            if not metrics:
                return
            
            fieldnames = list(metrics[0].keys())
            
            with open(filepath, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(metrics)
            
            logger.info(f"Exported {len(metrics)} metrics to {filepath}")
        except Exception as e:
            logger.error(f"Failed to export metrics to CSV: {e}")
