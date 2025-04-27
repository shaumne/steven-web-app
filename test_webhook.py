"""
Test script for the trading bot webhook - Modified for shares/stocks
"""
import requests
import json
import sys
import time

def test_webhook(url, alert_message=None, symbol=None, direction=None, price=None, test_mode=False):
    """
    Test the webhook endpoint with a share/stock alert
    
    Args:
        url (str): URL of the webhook endpoint
        alert_message (str, optional): Full alert message to send. If provided, other params are ignored.
        symbol (str, optional): Stock symbol (e.g. LSE_DLY:BTRW)
        direction (str, optional): UP or DOWN
        price (float, optional): Current price
        test_mode (bool, optional): Whether to run in test mode without real trades
    """
    # Eğer tam alert mesajı verilmişse, onu kullan
    if alert_message is not None:
        payload = {
            "message": alert_message,
            "timestamp": None,  # Let the server use the current time
            "test_mode": test_mode
        }
    # Aksi takdirde verilen parametrelerden mesaj oluştur
    elif symbol and direction and price:
        # Doğru format: "VIE_DLY:ANDR UP 57 0.5 1.016 1.189 1.312 1.414 1.494 1.554 1.599 1.632 1.656"
        # İlk sayı mevcut fiyat, sonrakiler ATR değerleri
        
        # Varsayılan ATR değerleri (gerçekçi değerler)
        atr_values = [0.5, 1.016, 1.189, 1.312, 1.414, 1.494, 1.554, 1.599, 1.632, 1.656]
        
        # Alert mesajını oluştur
        atr_str = " ".join(str(v) for v in atr_values)
        alert_message = f"{symbol} {direction} {price} {atr_str}"
        
        payload = {
            "message": alert_message,
            "timestamp": None,
            "test_mode": test_mode
        }
    else:
        # Eğer gerekli bilgiler verilmemişse varsayılan değerleri kullan
        # Bunlar demo hesapta çalışabilecek yaygın hisse değerleri
        if symbol is None:
            symbol = "LSE_DLY:BTRW"  # Barratt Developments PLC
        if direction is None:
            direction = "UP"
        if price is None:
            price = 175.2
            
        # Varsayılan ATR değerleri (gerçekçi değerler)
        atr_values = [0.5, 1.016, 1.189, 1.312, 1.414, 1.494, 1.554, 1.599, 1.632, 1.656]
        
        # Alert mesajını oluştur
        atr_str = " ".join(str(v) for v in atr_values)
        alert_message = f"{symbol} {direction} {price} {atr_str}"
        
        payload = {
            "message": alert_message,
            "timestamp": None,
            "test_mode": test_mode
        }
    
    # İşlem modunu göster
    mode_str = "TEST MODU" if test_mode else "GERÇEK İŞLEM MODU (DEMO HESAPTA)"
    print(f"Hisse Senedi İşlemi - {mode_str}")
    print(f"Sending alert to {url}: {alert_message}")
    
    # API isteğini yap
    try:
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        
        print(f"Response status code: {response.status_code}")
        print(f"Response content: {response.text}")
        
        if response.status_code == 200:
            print("İşlem başarılı!")
            
            # API yanıtını parse et
            try:
                result = response.json()
                if result.get("status") == "success":
                    print(f"Trade başarılı: {result.get('message', '')}")
                    
                    # İşlem detaylarını göster
                    print("\n*** İŞLEM DETAYLARI ***")
                    
                    # Deal reference (varsa)
                    deal_reference = result.get("deal_reference")
                    if deal_reference:
                        print(f"Deal Reference: {deal_reference}")
                        position_url = f"{url.replace('/webhook', '')}/position/status?reference={deal_reference}"
                        print(f"İşlem durumunu kontrol etmek için: {position_url}")
                        
                    # Epic
                    if "epic" in result:
                        print(f"Epic: {result.get('epic')}")
                    
                    # İşlem türü ve parametreleri
                    order_type = result.get("order_type", "")
                    if order_type:
                        print(f"İşlem Türü: {order_type}")
                    
                    # Yön
                    if "direction" in result:
                        print(f"Yön: {result.get('direction')}")
                    
                    # Fiyat
                    if "entry_price" in result:
                        print(f"Giriş Fiyatı: {result.get('entry_price')}")
                    
                    # Trade boyutu
                    if "size" in result:
                        print(f"İşlem Boyutu: {result.get('size')}")
                    
                    # Stop loss ve limit mesafeleri
                    if "stop_distance" in result:
                        print(f"Stop Loss Mesafesi: {result.get('stop_distance')}")
                    if "limit_distance" in result:
                        print(f"Limit Mesafesi: {result.get('limit_distance')}")
                    
                    print("**********************")
                    
                    # Limit işlemler için bilgi
                    if order_type == "LIMIT":
                        print("\nBu bir LIMIT emir. İşlem belirtilen fiyata ulaşıldığında gerçekleşecek.")
                        print(f"Tüm pozisyonları görmek için: {url.replace('/webhook', '')}/positions")
                else:
                    print(f"Trade hatası: {result.get('message', '')}")
            except Exception as e:
                print(f"API yanıtını işlerken hata: {e}")
        else:
            print(f"Hata: İstek durumu {response.status_code}")
            
    except Exception as e:
        print(f"İstek gönderirken hata oluştu: {e}")

if __name__ == "__main__":
    # Parse command line arguments
    if len(sys.argv) < 2:
        print("Kullanım:")
        print("1. Tam alert mesajı ile: python test_webhook.py <webhook_url> <alert_message>")
        print("2. Parametrelerle: python test_webhook.py <webhook_url> --symbol=LSE_DLY:BTRW --direction=UP --price=175.2 [--test]")
        print("\nÖrnek alert mesajı formatı:")
        print("VIE_DLY:ANDR UP 57 0.5 1.016 1.189 1.312 1.414 1.494 1.554 1.599 1.632 1.656")
        sys.exit(1)
    
    webhook_url = sys.argv[1]
    
    # Parametreleri parse et
    alert_message = None
    symbol = None
    direction = None
    price = None
    test_mode = False
    
    for arg in sys.argv[2:]:
        if arg == "--test":
            test_mode = True
        elif arg.startswith("--symbol="):
            symbol = arg.split("=")[1]
        elif arg.startswith("--direction="):
            direction = arg.split("=")[1]
        elif arg.startswith("--price="):
            price = float(arg.split("=")[1])
        elif not arg.startswith("--"):
            alert_message = arg
    
    # Güvenlik uyarısı - sadece gerçek işlem modunda sor
    if not test_mode:
        print("DİKKAT: Demo hesabınızda GERÇEK İŞLEMLER gerçekleştirilecek!")
        confirmation = input("Devam etmek istediğinize emin misiniz? (evet/hayır): ")
        if confirmation.lower() not in ["evet", "e", "yes", "y"]:
            print("İşlem iptal ediliyor...")
            sys.exit(0)
    
    # Test webhook'u çağır
    test_webhook(webhook_url, alert_message, symbol, direction, price, test_mode) 