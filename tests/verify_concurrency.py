import sys
import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Mock modules before importing backend.routers.classification
sys.modules['backend.database'] = MagicMock()
sys.modules['backend.services.ai_classifier'] = MagicMock()

from backend.routers.classification import analyze_all_endpoint
from backend.models import ProcessoData

async def mock_classify_process(process):
    print(f"Start classifying {process.numero}")
    await asyncio.sleep(0.5) # Simulate delay
    print(f"End classifying {process.numero}")
    return MagicMock()

async def test_concurrency():
    print("Testing concurrency limit...")
    
    # Setup mocks
    mock_db = [ProcessoData(numero=f"Proc-{i}", classeProcessual="7", competencia="Civel", movimentos=[], xml_raw="") for i in range(10)]
    
    with patch('backend.routers.classification.load_db', return_value=mock_db), \
         patch('backend.routers.classification.load_classifications', return_value=[]), \
         patch('backend.routers.classification.classify_process', side_effect=mock_classify_process) as mock_classify, \
         patch('backend.routers.classification.save_classification_result'):
        
        start_time = time.time()
        await analyze_all_endpoint(force=True)
        end_time = time.time()
        
        duration = end_time - start_time
        print(f"Total duration: {duration:.2f}s")
        
        # With 10 items and 0.5s delay and limit 5:
        # Batch 1 (5 items): 0.5s
        # Batch 2 (5 items): 0.5s
        # Total should be around 1.0s. If sequential, it would be 5.0s.
        
        if duration < 2.0:
            print("Concurrency check passed (fast enough)")
        else:
            print("Concurrency check failed (too slow)")
            
        assert mock_classify.call_count == 10

if __name__ == "__main__":
    asyncio.run(test_concurrency())
