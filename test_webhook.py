"""
Test script for the trading bot webhook
"""
import requests
import json
import sys

def test_webhook(url, alert_message=None, test_epic=False, live_mode=False):
    """
    Test the webhook endpoint with a sample alert
    
    Args:
        url (str): URL of the webhook endpoint
        alert_message (str, optional): Alert message to send. Defaults to a sample alert.
        test_epic (bool, optional): Whether to test EPIC retrieval. Defaults to False.
        live_mode (bool, optional): Whether to execute real trades. Defaults to False.
    """
    # Default test alert if none provided
    if alert_message is None:
        alert_message = "VIE_DLY:ANDR DOWN 7.51 50.53 48.22 45.44 42.65 41.23 40.89 40.55 40.22 40.09 40.01"

    # If testing EPIC retrieval, use a symbol that might not have a CSV entry
    if test_epic:
        alert_message = "VIE_DLY:ANDR DOWN 7.51 50.53 48.22 45.44 42.65 41.23 40.89 40.55 40.22 40.09 40.01"
        print("Testing EPIC retrieval with symbol: FTSE:TSCO")
    
    # Prepare the data
    payload = {
        "message": alert_message,
        "timestamp": None,  # Let the server use the current time
        "test_mode": False  # Gerçek işlem yapılması için test_mode'u False olarak ayarla
    }
    
    # Make the request
    mode_str = "GERÇEK İŞLEM MODU (DEMO HESAPTA)"
    print(f"Sending {mode_str} alert to {url}: {alert_message}")
    try:
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        
        print(f"Response status code: {response.status_code}")
        print(f"Response content: {response.text}")
        
        if response.status_code == 200:
            print("İşlem başarılı!")
        else:
            print(f"Hata: İstek durumu {response.status_code}")
            
    except Exception as e:
        print(f"İstek gönderirken hata oluştu: {e}")

if __name__ == "__main__":
    # Parse command line arguments
    if len(sys.argv) < 2:
        print("Kullanım: python test_webhook.py <webhook_url> [alert_message]")
        sys.exit(1)
    
    webhook_url = sys.argv[1]
    
    # Artık test_epic ve live_mode flag'leri kaldırıldı
    # Her zaman gerçek işlem modu kullanılacak
    
    # Güvenlik uyarısı
    print("DİKKAT: Demo hesabınızda GERÇEK İŞLEMLER gerçekleştirilecek!")
    confirmation = input("Devam etmek istediğinize emin misiniz? (evet/hayır): ")
    if confirmation.lower() not in ["evet", "e", "yes", "y"]:
        print("İşlem iptal ediliyor...")
        sys.exit(0)
    
    # If an alert message is provided
    alert_message = None
    for arg in sys.argv[2:]:
        if not arg.startswith("--"):
            alert_message = arg
            break
    
    test_webhook(webhook_url, alert_message, False, True) 