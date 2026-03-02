"""
Firebase Configuration Module for NSATE
CRITICAL: All state management MUST use Firebase per ecosystem constraints
Architectural Choice: Firestore chosen over RealtimeDB for complex document storage
"""
import os
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
import firebase_admin
from firebase_admin import credentials, firestore
from firebase_admin.exceptions import FirebaseError

logger = logging.getLogger(__name__)


@dataclass
class FirebaseConfig:
    """Validated Firebase configuration with edge case handling"""
    project_id: str
    credentials_path: Optional[str] = None
    database_url: Optional[str] = None
    
    def __post_init__(self) -> None:
        """Validate configuration before use"""
        if not self.project_id:
            raise ValueError("Firebase project_id is required")
        
        if self.credentials_path and not os.path.exists(self.credentials_path):
            logger.error(f"Firebase credentials file not found: {self.credentials_path}")
            raise FileNotFoundError(f"Credentials file not found: {self.credentials_path}")


class FirebaseClient:
    """Robust Firebase client with comprehensive error handling"""
    
    _instance: Optional['FirebaseClient'] = None
    _initialized: bool = False
    
    def __new__(cls, *args, **kwargs) -> 'FirebaseClient':
        """Singleton pattern for Firebase client"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: FirebaseConfig) -> None:
        """Initialize Firebase with validation and error recovery"""
        if self._initialized:
            return
            
        try:
            self.config = config
            self._validate_environment()
            
            # Initialize Firebase app
            if firebase_admin._apps:
                self.app = firebase_admin.get_app()
                logger.info("Using existing Firebase app")
            else:
                if config.credentials_path:
                    cred = credentials.Certificate(config.credentials_path)
                    self.app = firebase_admin.initialize_app(
                        credential=cred,
                        options={'projectId': config.project_id}
                    )
                else:
                    # Use default credentials (GCP environment)
                    self.app = firebase_admin.initialize_app(
                        options={'projectId': config.project_id}
                    )
                logger.info(f"Initialized Firebase app for project: {config.project_id}")
            
            # Initialize Firestore client
            self.db = firestore.client()
            self._test_connection()
            self._initialized = True
            
        except FirebaseError as e:
            logger.error(f"Firebase initialization error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during Firebase init: {str(e)}")
            raise
    
    def _validate_environment(self) -> None:
        """Validate environment variables and dependencies"""
        required_vars = ['GOOGLE_APPLICATION_CREDENTIALS']
        missing = [var for var in required_vars if not os.getenv(var)]
        
        if missing and not self.config.credentials_path:
            logger.warning(f"Missing environment variables: {missing}. Using explicit credentials path.")
    
    def _test_connection(self) -> None:
        """Test Firestore connection with timeout"""
        try:
            # Test with a simple document read
            test_ref = self.db.collection('_system').document('health')
            test_ref.set({'timestamp': firestore.SERVER_TIMESTAMP}, merge=True)
            logger.info("Firebase connection test successful")
        except Exception as e:
            logger.error(f"Firebase connection test failed: {str(e)}")
            raise
    
    def store_strategy_result(self, 
                             strategy_id: str, 
                             result_data: Dict[str, Any],
                             collection: str = 'strategy_results') -> str:
        """
        Store strategy results with validation and error handling
        """
        if not strategy_id:
            raise ValueError("strategy_id cannot be empty")
        
        if not result_data:
            raise ValueError("result_data cannot be empty")
        
        try:
            doc_ref = self.db.collection(collection).document(strategy_id)
            result_data['updated_at'] = firestore.SERVER_TIMESTAMP
            
            # Ensure required fields
            if 'created_at' not in result_data:
                result_data['created_at'] = firestore.SERVER_TIMESTAMP
            
            doc_ref.set(result_data, merge=True)
            logger.info(f"Stored strategy result for ID: {strategy_id}")
            return doc_ref.id
            
        except FirebaseError as e:
            logger.error(f"Firestore write error for strategy {strategy_id}: {str(e)}")
            raise
    
    def get_market_data(self, 
                       symbol: str, 
                       timeframe: str = '1h',
                       limit: int = 1000) -> Optional[Dict[str, Any]]:
        """
        Retrieve market data from Firestore with validation
        """
        if not symbol:
            raise ValueError("symbol cannot be empty")
        
        valid_timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']
        if timeframe not in valid_timeframes:
            raise ValueError(f"time