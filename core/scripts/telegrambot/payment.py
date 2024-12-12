import hashlib
import hmac
import json
import requests
from datetime import datetime
import time

class CryptomusPayment:
    def __init__(self, merchant_id, payment_key):
        self.merchant_id = merchant_id
        self.payment_key = payment_key
        self.base_url = "https://api.cryptomus.com/v1"
        
    def _sign(self, payload):
        encoded = json.dumps(payload, separators=(',', ':')).encode()
        sign = hmac.new(
            self.payment_key.encode(),
            encoded,
            hashlib.sha512
        ).hexdigest()
        return sign
        
    def create_payment(self, amount, currency, order_id, success_url=None, callback_url=None):
        endpoint = f"{self.base_url}/payment"
        
        payload = {
            "amount": str(amount),
            "currency": currency,
            "order_id": order_id,
            "network": "tron",
            "currency_in": "USDT",
            "to_currency": "USDT"
        }
        
        if success_url:
            payload["url_return"] = success_url
        if callback_url:
            payload["url_callback"] = callback_url
            
        sign = self._sign(payload)
        
        headers = {
            "merchant": self.merchant_id,
            "sign": sign,
            "Content-Type": "application/json"
        }
        
        response = requests.post(endpoint, json=payload, headers=headers)
        return response.json()
        
    def check_payment(self, uuid):
        endpoint = f"{self.base_url}/payment/info"
        
        payload = {
            "uuid": uuid
        }
        
        sign = self._sign(payload)
        
        headers = {
            "merchant": self.merchant_id,
            "sign": sign,
            "Content-Type": "application/json"
        }
        
        response = requests.post(endpoint, json=payload, headers=headers)
        return response.json()

class PaymentManager:
    def __init__(self, config_file):
        self.config_file = config_file
        self.load_config()
        
    def load_config(self):
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                self.merchant_id = config.get('merchant_id', '')
                self.payment_key = config.get('payment_key', '')
                self.enabled = config.get('enabled', False)
        except Exception:
            self.merchant_id = ''
            self.payment_key = ''
            self.enabled = False
            
    def is_enabled(self):
        return self.enabled and self.merchant_id and self.payment_key
        
    def create_payment(self, amount, plan_type, user_id):
        if not self.is_enabled():
            return None
            
        payment_handler = CryptomusPayment(self.merchant_id, self.payment_key)
        order_id = f"{user_id}_{plan_type}_{int(time.time())}"
        
        try:
            result = payment_handler.create_payment(
                amount=amount,
                currency="USD",
                order_id=order_id
            )
            
            if result.get('status') == 'success':
                return {
                    'payment_url': result['result'].get('url'),
                    'uuid': result['result'].get('uuid'),
                    'order_id': order_id,
                    'amount': amount,
                    'plan_type': plan_type
                }
        except Exception:
            pass
            
        return None
        
    def check_payment_status(self, uuid):
        if not self.is_enabled():
            return None
            
        payment_handler = CryptomusPayment(self.merchant_id, self.payment_key)
        
        try:
            result = payment_handler.check_payment(uuid)
            if result.get('status') == 'success':
                payment_status = result['result'].get('payment_status')
                return payment_status
        except Exception:
            pass
            
        return None
