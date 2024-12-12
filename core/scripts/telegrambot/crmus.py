import os
import hmac
import json
import hashlib
import requests
from typing import Dict, Optional, Any, Union
from datetime import datetime

CRMUS_DATA_FILE = "/etc/hysteria/crmus_data.json"

class CryptomusConfig:
    """Configuration manager for Cryptomus credentials"""
    
    @staticmethod
    def load_config() -> Dict[str, Any]:
        """Load Cryptomus configuration from file"""
        if os.path.exists(CRMUS_DATA_FILE):
            try:
                with open(CRMUS_DATA_FILE, 'r') as f:
                    return json.load(f)
            except Exception:
                return {"merchant_uuid": "", "payment_key": "", "test_mode": True, "payments": {}}
        return {"merchant_uuid": "", "payment_key": "", "test_mode": True, "payments": {}}
    
    @staticmethod
    def save_config(config: Dict[str, Any]) -> None:
        """Save Cryptomus configuration to file"""
        os.makedirs(os.path.dirname(CRMUS_DATA_FILE), exist_ok=True)
        with open(CRMUS_DATA_FILE, 'w') as f:
            json.dump(config, f, indent=4)
    
    @staticmethod
    def update_credentials(merchant_uuid: str, payment_key: str, test_mode: bool = False) -> None:
        """Update Cryptomus credentials"""
        config = CryptomusConfig.load_config()
        config.update({
            "merchant_uuid": merchant_uuid,
            "payment_key": payment_key,
            "test_mode": test_mode
        })
        CryptomusConfig.save_config(config)
    
    @staticmethod
    def get_credentials() -> tuple[str, str, bool]:
        """Get current Cryptomus credentials"""
        config = CryptomusConfig.load_config()
        return (
            config.get("merchant_uuid", ""),
            config.get("payment_key", ""),
            config.get("test_mode", True)
        )
    
    @staticmethod
    def is_configured() -> bool:
        """Check if Cryptomus is configured"""
        uuid, key, _ = CryptomusConfig.get_credentials()
        return bool(uuid and key)
    
    @staticmethod
    def save_payment_data(payment_data: Dict[str, Any]) -> None:
        """Save payment data to storage"""
        config = CryptomusConfig.load_config()
        payments = config.get("payments", {})
        order_id = payment_data.get("order_id")
        if order_id:
            payments[order_id] = payment_data
            config["payments"] = payments
            CryptomusConfig.save_config(config)
    
    @staticmethod
    def get_payment_data(order_id: str) -> Optional[Dict[str, Any]]:
        """Get payment data from storage"""
        config = CryptomusConfig.load_config()
        return config.get("payments", {}).get(order_id)

class CryptomusClient:
    """
    Cryptomus Payment System Client
    Documentation: https://doc.cryptomus.com/
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CryptomusClient, cls).__new__(cls)
            # Initialize with saved credentials
            merchant_uuid, payment_key, test_mode = CryptomusConfig.get_credentials()
            cls._instance.merchant_uuid = merchant_uuid
            cls._instance.payment_key = payment_key
            cls._instance.test_mode = test_mode
            cls._instance.base_url = "https://api.cryptomus.com/v1"
        return cls._instance
    
    def update_credentials(self, merchant_uuid: str, payment_key: str, test_mode: bool = False):
        """Update client credentials"""
        self.merchant_uuid = merchant_uuid
        self.payment_key = payment_key
        self.test_mode = test_mode
        CryptomusConfig.update_credentials(merchant_uuid, payment_key, test_mode)
        
    def _generate_sign(self, payload: Dict) -> str:
        """Generate signature for Cryptomus API requests"""
        if not self.merchant_uuid or not self.payment_key:
            raise ValueError("Cryptomus credentials not configured")
            
        encoded_payload = json.dumps(payload, separators=(',', ':'))
        return hmac.new(
            self.payment_key.encode('utf-8'),
            encoded_payload.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()
        
    def _make_request(self, endpoint: str, payload: Dict) -> Dict:
        """Make request to Cryptomus API"""
        if not self.merchant_uuid or not self.payment_key:
            raise ValueError("Cryptomus credentials not configured")
            
        headers = {
            'merchant': self.merchant_uuid,
            'sign': self._generate_sign(payload),
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            f"{self.base_url}/{endpoint}",
            headers=headers,
            json=payload
        )
        
        response.raise_for_status()
        return response.json()
        
    def create_payment(
        self,
        amount: float,
        currency: str,
        order_id: str,
        network: Optional[str] = None,
        currency_in: Optional[str] = None,
        lifetime: int = 7200,
        url_return: Optional[str] = None,
        url_callback: Optional[str] = None,
        is_payment_multiple: bool = False,
        additional_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Create a new payment"""
        payload = {
            "amount": str(amount),
            "currency": currency,
            "order_id": order_id,
            "lifetime": lifetime,
            "is_payment_multiple": is_payment_multiple,
            "test": self.test_mode
        }
        
        if network:
            payload["network"] = network
        if currency_in:
            payload["currency_in"] = currency_in
        if url_return:
            payload["url_return"] = url_return
        if url_callback:
            payload["url_callback"] = url_callback
        if additional_data:
            payload["additional_data"] = additional_data
            
        response = self._make_request("payment", payload)
        if response.get("result"):
            CryptomusConfig.save_payment_data(response["result"])
        return response
        
    def get_payment(self, payment_id: str = None, order_id: str = None) -> Dict[str, Any]:
        """Get payment information"""
        if not payment_id and not order_id:
            raise ValueError("Either payment_id or order_id must be provided")
            
        # First try to get from local storage
        if order_id and (stored_data := CryptomusConfig.get_payment_data(order_id)):
            return {"result": stored_data}
            
        payload = {}
        if payment_id:
            payload["uuid"] = payment_id
        if order_id:
            payload["order_id"] = order_id
            
        response = self._make_request("payment/info", payload)
        if response.get("result"):
            CryptomusConfig.save_payment_data(response["result"])
        return response
        
    def get_payment_status(self, payment_id: str = None, order_id: str = None) -> str:
        """Get payment status"""
        payment_info = self.get_payment(payment_id, order_id)
        return payment_info.get("result", {}).get("status", "unknown")
        
    def verify_webhook(self, webhook_data: Dict, signature: str) -> bool:
        """Verify webhook signature"""
        calculated_sign = self._generate_sign(webhook_data)
        return hmac.compare_digest(calculated_sign.lower(), signature.lower())
        
    def get_payment_history(
        self,
        cursor: int = 0,
        limit: int = 25,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get payment history"""
        payload = {
            "cursor": cursor,
            "limit": limit
        }
        
        if date_from:
            payload["date_from"] = int(date_from.timestamp())
        if date_to:
            payload["date_to"] = int(date_to.timestamp())
            
        return self._make_request("payment/list", payload)

# Payment status constants
class PaymentStatus:
    PAID = "paid"
    PAID_OVER = "paid_over"
    WRONG_AMOUNT = "wrong_amount"
    PROCESS = "process"
    EXPIRED = "expired"
    CANCEL = "cancel"
    SYSTEM_FAIL = "system_fail"
    REFUND = "refund"
    WRONG_AMOUNT_WAITING = "wrong_amount_waiting"
