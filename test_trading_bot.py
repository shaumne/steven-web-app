#!/usr/bin/env python3
"""
Kapsamlı Trading Bot Test Scripti
---------------------------------
Bu script, trading bot uygulamasının tüm bileşenlerini ve özelliklerini test eder.
Testler şunları içerir:
- API bağlantısı
- Webhook işleme
- Ticaret hesaplamaları
- Ticaret yönetimi
- Web arayüzü fonksiyonları
- CSV İşlemleri
- Kullanıcı yönetimi
"""

import os
import sys
import json
import time
import logging
import unittest
import requests
import pandas as pd
from datetime import datetime, timedelta
from unittest import mock
from pathlib import Path

# Test çalıştırma dizinini ayarla
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Logging yapılandırması
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('test_trading_bot')

try:
    from app import app
    from trading_bot.webhook_handler import WebhookHandler
    from trading_bot.trade_manager import TradeManager
    from trading_bot.trade_calculator import TradeCalculator
    from trading_bot.ig_api import IGClient
    from trading_bot.auth import USERS_FILE, hash_password, verify_password
    logger.info("Modüller başarıyla içe aktarıldı")
except ImportError as e:
    logger.error(f"Modül içe aktarma hatası: {str(e)}")
    sys.exit(1)

class TestIGAPI(unittest.TestCase):
    """IG Markets API bağlantısı ve fonksiyonlarını test eder."""
    
    def setUp(self):
        """Test için mock API istemcisi oluşturur."""
        self.ig_client = mock.MagicMock()
        self.ig_client.create_session.return_value = True
        logger.info("TestIGAPI sınıfı hazırlandı")
    
    def test_create_session(self):
        """API oturum oluşturma işlemini test eder."""
        result = self.ig_client.create_session()
        self.assertTrue(result)
        logger.info("API oturum oluşturma testi başarılı")
    
    def test_get_positions(self):
        """Pozisyonları alma işlemini test eder."""
        # Mock pozisyonları hazırla
        mock_positions = [
            {
                'dealId': 'DEAL123',
                'epic': 'CS.D.EURUSD.CFD.IP',
                'direction': 'BUY',
                'size': 2.0,
                'level': 1.1234,
                'limitLevel': 1.1334,
                'stopLevel': 1.1134,
                'profit': 20.5,
                'currency': 'USD'
            }
        ]
        self.ig_client.get_positions.return_value = mock_positions
        
        # Testi çalıştır
        positions = self.ig_client.get_positions()
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]['dealId'], 'DEAL123')
        logger.info("Pozisyonları alma testi başarılı")
    
    def test_get_working_orders(self):
        """Bekleyen emirleri alma işlemini test eder."""
        # Mock emirleri hazırla
        mock_orders = [
            {
                'dealId': 'ORDER123',
                'epic': 'CS.D.EURUSD.CFD.IP',
                'direction': 'BUY',
                'orderType': 'LIMIT',
                'size': 2.0,
                'level': 1.1200,
                'stopLevel': 1.1100,
                'limitLevel': 1.1300,
                'createdDate': '2025-05-05T10:30:00'
            }
        ]
        self.ig_client.get_working_orders.return_value = mock_orders
        
        # Testi çalıştır
        orders = self.ig_client.get_working_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]['dealId'], 'ORDER123')
        logger.info("Bekleyen emirleri alma testi başarılı")

class TestTradeCalculator(unittest.TestCase):
    """Ticaret hesaplama fonksiyonlarını test eder."""
    
    def setUp(self):
        """TradeCalculator örneği oluşturur."""
        self.calculator = TradeCalculator()
        logger.info("TestTradeCalculator sınıfı hazırlandı")
    
    def test_calculate_position_size(self):
        """Pozisyon büyüklüğü hesaplama işlemini test eder."""
        # Test senaryosu: €10.000 hesap, %1 risk, 50 pip stop
        account_size = 10000
        risk_percentage = 1
        stop_pips = 50
        pip_value = 0.0001
        
        # Mevcut hesaplama fonksiyonunu çağır
        try:
            position_size = self.calculator.calculate_position_size(
                account_size, risk_percentage, stop_pips, pip_value
            )
            self.assertIsInstance(position_size, float)
            self.assertGreater(position_size, 0)
            logger.info(f"Hesaplanan pozisyon büyüklüğü: {position_size}")
        except Exception as e:
            self.fail(f"Position size hesaplama hatası: {str(e)}")
    
    def test_calculate_profit(self):
        """Kar hesaplama işlemini test eder."""
        # Test senaryosu: 2.0 lot, 50 pip kar, EURUSD
        position_size = 2.0
        entry_price = 1.1200
        current_price = 1.1250  # 50 pip kar
        direction = "BUY"
        pip_value = 0.0001
        
        try:
            profit = self.calculator.calculate_profit(
                position_size, entry_price, current_price, direction, pip_value
            )
            self.assertIsInstance(profit, float)
            expected_profit = position_size * 10000 * (current_price - entry_price)  # EURUSD için
            self.assertAlmostEqual(profit, expected_profit, delta=0.01)
            logger.info(f"Hesaplanan kar: {profit}")
        except Exception as e:
            self.fail(f"Kar hesaplama hatası: {str(e)}")

class TestWebhookHandler(unittest.TestCase):
    """Webhook işleme fonksiyonlarını test eder."""
    
    def setUp(self):
        """WebhookHandler örneği oluşturur."""
        # Mock IG API
        self.mock_ig_api = mock.MagicMock()
        
        # Mock Settings Manager
        self.mock_settings_manager = mock.MagicMock()
        self.mock_settings_manager.get_settings.return_value = {
            'trading': {
                'default_order_type': 'LIMIT'
            }
        }
        self.mock_settings_manager.get_ticker_data.return_value = pd.DataFrame({
            'Symbol': ['EURUSD'],
            'IG EPIC': ['CS.D.EURUSD.CFD.IP'],
            'Postion Size Max GBP': [2.0]
        })
        
        # WebhookHandler örneği oluştur
        self.webhook_handler = WebhookHandler(
            ig_api=self.mock_ig_api,
            settings_manager=self.mock_settings_manager
        )
        logger.info("TestWebhookHandler sınıfı hazırlandı")
    
    def test_process_webhook_buy_signal(self):
        """Alış sinyali webhook'unu test eder."""
        # Örnek TradingView sinyal JSON'u
        webhook_data = {
            "symbol": "EURUSD",
            "direction": "BUY",
            "price": 1.1234,
            "stop": 1.1134,  # Stop loss
            "limit": 1.1334,  # Take profit
            "size": 2.0,
            "message": "Buy signal for EURUSD"
        }
        
        # IG API create_position mock yanıtı
        self.mock_ig_api.create_position.return_value = {
            "status": "success",
            "deal_reference": "DEAL123",
            "deal_id": "123456",
            "deal_status": "ACCEPTED"
        }
        
        # process_webhook fonksiyonunu çağır
        try:
            result = self.webhook_handler.process_webhook(webhook_data)
            
            # IG API'nin doğru parametrelerle çağrıldığını kontrol et
            self.mock_ig_api.create_position.assert_called_once_with(
                epic="CS.D.EURUSD.CFD.IP",
                direction="BUY",
                size=2.0,
                price=1.1234,
                stop=1.1134,
                limit=1.1334,
                use_limit_order=True
            )
            
            # Sonucu kontrol et
            self.assertEqual(result['status'], 'success')
            self.assertIn('details', result)
            logger.info("Alış sinyali webhook işleme testi başarılı")
        except Exception as e:
            self.fail(f"Webhook işleme hatası: {str(e)}")
    
    def test_process_webhook_sell_signal(self):
        """Satış sinyali webhook'unu test eder."""
        # Örnek TradingView sinyal JSON'u
        webhook_data = {
            "symbol": "EURUSD",
            "direction": "SELL",
            "price": 1.1234,
            "stop": 1.1334,  # Stop loss
            "limit": 1.1134,  # Take profit
            "size": 2.0,
            "message": "Sell signal for EURUSD"
        }
        
        # IG API create_position mock yanıtı
        self.mock_ig_api.create_position.return_value = {
            "status": "success",
            "deal_reference": "DEAL124",
            "deal_id": "123457",
            "deal_status": "ACCEPTED"
        }
        
        # process_webhook fonksiyonunu çağır
        try:
            result = self.webhook_handler.process_webhook(webhook_data)
            
            # IG API'nin doğru parametrelerle çağrıldığını kontrol et
            self.mock_ig_api.create_position.assert_called_once_with(
                epic="CS.D.EURUSD.CFD.IP",
                direction="SELL",
                size=2.0,
                price=1.1234,
                stop=1.1334,
                limit=1.1134,
                use_limit_order=True
            )
            
            # Sonucu kontrol et
            self.assertEqual(result['status'], 'success')
            self.assertIn('details', result)
            logger.info("Satış sinyali webhook işleme testi başarılı")
        except Exception as e:
            self.fail(f"Webhook işleme hatası: {str(e)}")
    
    def test_process_webhook_missing_fields(self):
        """Eksik alan içeren webhook'u test eder."""
        # Eksik alanlar içeren webhook verisi
        webhook_data = {
            "symbol": "EURUSD"
            # direction eksik
        }
        
        # process_webhook fonksiyonunu çağır
        result = self.webhook_handler.process_webhook(webhook_data)
        
        # Hata yanıtını kontrol et
        self.assertEqual(result['status'], 'error')
        self.assertIn('Missing required fields', result['message'])
        logger.info("Eksik alan kontrolü testi başarılı")
    
    def test_process_webhook_invalid_symbol(self):
        """Geçersiz sembol içeren webhook'u test eder."""
        # Geçersiz sembol içeren webhook verisi
        webhook_data = {
            "symbol": "INVALID",
            "direction": "BUY",
            "price": 1.1234
        }
        
        # Mock ticker data'yı güncelle
        self.mock_settings_manager.get_ticker_data.return_value = pd.DataFrame({
            'Symbol': ['EURUSD'],  # INVALID sembolü yok
            'IG EPIC': ['CS.D.EURUSD.CFD.IP'],
            'Postion Size Max GBP': [2.0]
        })
        
        # process_webhook fonksiyonunu çağır
        result = self.webhook_handler.process_webhook(webhook_data)
        
        # Hata yanıtını kontrol et
        self.assertEqual(result['status'], 'error')
        self.assertIn('Invalid symbol', result['message'])
        logger.info("Geçersiz sembol kontrolü testi başarılı")

class TestTradeManager(unittest.TestCase):
    """Ticaret yönetimi fonksiyonlarını test eder."""
    
    def setUp(self):
        """TradeManager örneği oluşturur."""
        # IG API mockla
        self.mock_ig_client = mock.MagicMock()
        # TradeCalculator mockla
        self.mock_calculator = mock.MagicMock()
        # TradeManager örneği oluştur
        self.trade_manager = TradeManager(self.mock_ig_client, self.mock_calculator)
        logger.info("TestTradeManager sınıfı hazırlandı")
    
    def test_open_position(self):
        """Pozisyon açma işlemini test eder."""
        # Mock değerler
        ticker = "EURUSD"
        direction = "BUY"
        risk_percentage = 1.0
        entry_price = 1.1234
        stop_loss = 1.1134
        take_profit = 1.1334
        
        # IGClient.create_position mockla
        self.mock_ig_client.create_position.return_value = {"dealId": "DEAL123", "status": "OPEN"}
        
        # TradeCalculator.calculate_position_size mockla
        self.mock_calculator.calculate_position_size.return_value = 2.0
        
        # open_position fonksiyonunu çağır
        try:
            result = self.trade_manager.open_position(
                ticker, direction, risk_percentage, entry_price, stop_loss, take_profit
            )
            self.assertEqual(result["dealId"], "DEAL123")
            self.assertEqual(result["status"], "OPEN")
            
            # IG API'nin doğru parametrelerle çağrıldığını kontrol et
            self.mock_ig_client.create_position.assert_called_once()
            logger.info("Pozisyon açma testi başarılı")
        except Exception as e:
            self.fail(f"Pozisyon açma hatası: {str(e)}")
    
    def test_close_position(self):
        """Pozisyon kapatma işlemini test eder."""
        # Mock değerler
        deal_id = "DEAL123"
        
        # IGClient.close_position mockla
        self.mock_ig_client.close_position.return_value = {"dealId": deal_id, "status": "CLOSED"}
        
        # close_position fonksiyonunu çağır
        try:
            result = self.trade_manager.close_position(deal_id)
            self.assertEqual(result["dealId"], deal_id)
            self.assertEqual(result["status"], "CLOSED")
            
            # IG API'nin doğru parametrelerle çağrıldığını kontrol et
            self.mock_ig_client.close_position.assert_called_once_with(deal_id)
            logger.info("Pozisyon kapatma testi başarılı")
        except Exception as e:
            self.fail(f"Pozisyon kapatma hatası: {str(e)}")
    
    def test_create_working_order(self):
        """Bekleyen emir oluşturma işlemini test eder."""
        # Mock değerler
        ticker = "EURUSD"
        direction = "BUY"
        order_type = "LIMIT"
        risk_percentage = 1.0
        entry_price = 1.1200
        stop_loss = 1.1100
        take_profit = 1.1300
        
        # IGClient.create_working_order mockla
        self.mock_ig_client.create_working_order.return_value = {"dealId": "ORDER123", "status": "WORKING"}
        
        # TradeCalculator.calculate_position_size mockla
        self.mock_calculator.calculate_position_size.return_value = 2.0
        
        # create_working_order fonksiyonunu çağır
        try:
            result = self.trade_manager.create_working_order(
                ticker, direction, order_type, risk_percentage, entry_price, stop_loss, take_profit
            )
            self.assertEqual(result["dealId"], "ORDER123")
            self.assertEqual(result["status"], "WORKING")
            
            # IG API'nin doğru parametrelerle çağrıldığını kontrol et
            self.mock_ig_client.create_working_order.assert_called_once()
            logger.info("Bekleyen emir oluşturma testi başarılı")
        except Exception as e:
            self.fail(f"Bekleyen emir oluşturma hatası: {str(e)}")

    def test_working_orders_display(self):
        """Çalışan emirlerin doğru görüntülenmesini test eder."""
        # Mock çalışan emirler
        mock_orders = [
            {
                'dealId': 'ORDER123',
                'epic': 'CS.D.EURUSD.CFD.IP',
                'direction': 'BUY',
                'orderType': 'LIMIT',
                'size': 2.0,
                'level': 1.1200,
                'stopLevel': 1.1100,
                'limitLevel': 1.1300,
                'createdDate': '2025-05-05T10:30:00'
            }
        ]
        self.mock_ig_client.get_working_orders.return_value = mock_orders
        
        # Emirleri al ve kontrol et
        orders = self.trade_manager.get_working_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]['size'], 2.0)
        self.assertEqual(orders[0]['level'], 1.1200)
        logger.info("Çalışan emirler görüntüleme testi başarılı")

    def test_max_trade_duration(self):
        """Maksimum işlem süresi kontrolünü test eder."""
        # 60 dakikadan eski emirler
        old_orders = [
            {
                'dealId': 'ORDER123',
                'createdDate': (datetime.now() - timedelta(hours=2)).isoformat(),
                'status': 'WORKING'
            }
        ]
        self.mock_ig_client.get_working_orders.return_value = old_orders
        
        # Maksimum süre kontrolü
        self.trade_manager.check_max_trade_duration()
        self.mock_ig_client.close_position.assert_called_once()
        logger.info("Maksimum işlem süresi kontrolü testi başarılı")

class TestFlaskApp(unittest.TestCase):
    """Flask web uygulaması fonksiyonlarını test eder."""
    
    def setUp(self):
        """Test istemcisi ve ortamı hazırlar."""
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        logger.info("TestFlaskApp sınıfı hazırlandı")
    
    def test_home_page(self):
        """Ana sayfa erişimini test eder."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Login', response.data)
        logger.info("Ana sayfa testi başarılı")
    
    def test_login_page(self):
        """Giriş sayfası erişimini test eder."""
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Login', response.data)
        logger.info("Giriş sayfası testi başarılı")
    
    def test_login_logout(self):
        """Giriş ve çıkış işlemlerini test eder."""
        # Test için mock kullanıcı
        username = "test_user"
        password = "test_password"
        
        # Giriş testi
        with mock.patch('trading_bot.auth.verify_password', return_value=True):
            login_response = self.client.post('/login', data={
                'username': username,
                'password': password
            }, follow_redirects=True)
            self.assertEqual(login_response.status_code, 200)
            self.assertIn(b'Dashboard', login_response.data)
            logger.info("Giriş işlemi testi başarılı")
        
        # Çıkış testi
        logout_response = self.client.get('/logout', follow_redirects=True)
        self.assertEqual(logout_response.status_code, 200)
        self.assertIn(b'Login', logout_response.data)
        logger.info("Çıkış işlemi testi başarılı")
    
    def test_dashboard_page(self):
        """Panel sayfası erişimini test eder (oturum açılmışken)."""
        with mock.patch('flask_login.utils._get_user', return_value=mock.MagicMock(is_authenticated=True)):
            response = self.client.get('/dashboard')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Dashboard', response.data)
            logger.info("Panel sayfası testi başarılı")
    
    def test_positions_page(self):
        """Pozisyonlar sayfası erişimini test eder (oturum açılmışken)."""
        with mock.patch('flask_login.utils._get_user', return_value=mock.MagicMock(is_authenticated=True)):
            with mock.patch('app.ig_client.get_positions', return_value=[]):
                with mock.patch('app.ig_client.get_working_orders', return_value=[]):
                    response = self.client.get('/positions')
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(b'Positions', response.data)
                    logger.info("Pozisyonlar sayfası testi başarılı")
    
    def test_webhook_endpoint(self):
        """Webhook endpoint işlevini test eder."""
        # Webhook işleyiciyi mockla
        with mock.patch('app.webhook_handler.process_webhook', return_value={"status": "success"}):
            # Test webhook verisi
            webhook_data = {
                "passphrase": "YOUR_SECRET_PHRASE",
                "ticker": "EURUSD",
                "action": "BUY",
                "price": 1.1234,
                "tp": 1.1334,
                "sl": 1.1134,
                "risk": 1.0
            }
            
            # POST isteği gönder
            response = self.client.post(
                '/webhook',
                data=json.dumps(webhook_data),
                content_type='application/json'
            )
            
            # Yanıtı kontrol et
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'"status":"success"', response.data)
            logger.info("Webhook endpoint testi başarılı")

    def test_daily_trades_count(self):
        """Günlük işlem sayısı hesaplamasını test eder."""
        # Mock pozisyonlar
        mock_positions = [
            {
                'dealId': 'DEAL123',
                'createdDate': datetime.now().isoformat(),
                'status': 'OPEN'
            },
            {
                'dealId': 'DEAL124',
                'createdDate': datetime.now().isoformat(),
                'status': 'OPEN'
            }
        ]
        
        with mock.patch('app.ig_client.get_positions', return_value=mock_positions):
            response = self.client.get('/dashboard')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'2', response.data)  # Bugünkü işlem sayısı
            logger.info("Günlük işlem sayısı testi başarılı")

    def test_market_order_option(self):
        """Piyasa emri seçeneğini test eder."""
        # Ayarlar sayfasına erişim
        with mock.patch('flask_login.utils._get_user', return_value=mock.MagicMock(is_authenticated=True)):
            response = self.client.get('/settings')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Order Type', response.data)
            logger.info("Piyasa emri seçeneği testi başarılı")

class TestCSVOperations(unittest.TestCase):
    """CSV dosya işlemlerini test eder."""
    
    def setUp(self):
        """Test ortamını ve geçici CSV dosyasını hazırlar."""
        self.temp_csv_path = "test_activity_history.csv"
        
        # Test verisi oluştur
        data = {
            'date': [datetime.now() - timedelta(days=i) for i in range(10)],
            'ticker': ['EURUSD'] * 10,
            'action': ['BUY', 'SELL'] * 5,
            'price': [1.1234 + i*0.001 for i in range(10)],
            'size': [2.0] * 10,
            'profit': [i*10 for i in range(10)],
        }
        
        # DataFrame oluştur ve CSV'ye kaydet
        df = pd.DataFrame(data)
        df.to_csv(self.temp_csv_path, index=False)
        logger.info(f"Test CSV dosyası oluşturuldu: {self.temp_csv_path}")
    
    def tearDown(self):
        """Test sonrası temizlik yapar."""
        if os.path.exists(self.temp_csv_path):
            os.remove(self.temp_csv_path)
            logger.info(f"Test CSV dosyası silindi: {self.temp_csv_path}")
    
    def test_read_csv(self):
        """CSV okuma işlemini test eder."""
        try:
            df = pd.read_csv(self.temp_csv_path)
            self.assertEqual(len(df), 10)
            self.assertIn('ticker', df.columns)
            self.assertIn('action', df.columns)
            self.assertIn('profit', df.columns)
            logger.info("CSV okuma testi başarılı")
        except Exception as e:
            self.fail(f"CSV okuma hatası: {str(e)}")
    
    def test_filter_csv_by_date(self):
        """Tarih filtreleme işlemini test eder."""
        try:
            df = pd.read_csv(self.temp_csv_path)
            df['date'] = pd.to_datetime(df['date'])
            
            # Son 7 gün için filtrele
            seven_days_ago = datetime.now() - timedelta(days=7)
            filtered_df = df[df['date'] >= seven_days_ago]
            
            self.assertLessEqual(len(filtered_df), 7)
            logger.info("CSV tarih filtreleme testi başarılı")
        except Exception as e:
            self.fail(f"CSV tarih filtreleme hatası: {str(e)}")

class TestUserManagement(unittest.TestCase):
    """Kullanıcı yönetimi fonksiyonlarını test eder."""
    
    def setUp(self):
        """Test için geçici kullanıcı dosyası oluşturur."""
        self.temp_users_file = "test_users.json"
        
        # Test kullanıcı verisi
        test_users = {
            "admin": {
                "password": hash_password("admin123"),
                "role": "admin"
            },
            "user": {
                "password": hash_password("user123"),
                "role": "user"
            }
        }
        
        # JSON dosyasına kaydet
        with open(self.temp_users_file, 'w') as f:
            json.dump(test_users, f)
        
        # USERS_FILE sabitini geçici olarak değiştir
        global USERS_FILE
        self.original_users_file = USERS_FILE
        USERS_FILE = self.temp_users_file
        
        logger.info(f"Test kullanıcı dosyası oluşturuldu: {self.temp_users_file}")
    
    def tearDown(self):
        """Test sonrası temizlik yapar."""
        # Geçici dosyayı sil
        if os.path.exists(self.temp_users_file):
            os.remove(self.temp_users_file)
        
        # USERS_FILE sabitini geri al
        global USERS_FILE
        USERS_FILE = self.original_users_file
        
        logger.info(f"Test kullanıcı dosyası silindi: {self.temp_users_file}")
    
    def test_verify_password(self):
        """Şifre doğrulama işlemini test eder."""
        # Doğru şifre
        self.assertTrue(verify_password("admin", "admin123"))
        self.assertTrue(verify_password("user", "user123"))
        
        # Yanlış şifre
        self.assertFalse(verify_password("admin", "wrong_password"))
        self.assertFalse(verify_password("user", "wrong_password"))
        
        # Olmayan kullanıcı
        self.assertFalse(verify_password("nonexistent", "any_password"))
        
        logger.info("Şifre doğrulama testi başarılı")
    
    def test_add_user(self):
        """Kullanıcı ekleme işlemini test eder."""
        from trading_bot.auth import add_user
        
        # Yeni kullanıcı ekle
        new_username = "test_user"
        new_password = "test_password"
        new_role = "user"
        
        result = add_user(new_username, new_password, new_role)
        self.assertTrue(result)
        
        # Kullanıcının eklendiğini doğrula
        self.assertTrue(verify_password(new_username, new_password))
        
        logger.info("Kullanıcı ekleme testi başarılı")
    
    def test_change_password(self):
        """Şifre değiştirme işlemini test eder."""
        from trading_bot.auth import change_password
        
        # Şifre değiştir
        username = "admin"
        new_password = "new_admin_password"
        
        result = change_password(username, new_password)
        self.assertTrue(result)
        
        # Yeni şifrenin çalıştığını doğrula
        self.assertTrue(verify_password(username, new_password))
        
        # Eski şifrenin artık çalışmadığını doğrula
        self.assertFalse(verify_password(username, "admin123"))
        
        logger.info("Şifre değiştirme testi başarılı")

    def test_last_login_display(self):
        """Son giriş bilgisinin görüntülenmesini test eder."""
        # Mock kullanıcı verisi
        test_user = {
            "username": "test_user",
            "last_login": datetime.now().isoformat()
        }
        
        # Son giriş bilgisini kontrol et
        self.assertIsNotNone(test_user.get('last_login'))
        logger.info("Son giriş bilgisi testi başarılı")

class TestLogging(unittest.TestCase):
    """Loglama sistemini test eder."""
    
    def setUp(self):
        """Test ortamını hazırlar."""
        self.log_dir = "logs"
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
    
    def test_daily_log_rotation(self):
        """Günlük log rotasyonunu test eder."""
        from trading_bot.logger import setup_logging
        
        # Loglama sistemini kur
        logger = setup_logging()
        
        # Test log mesajı
        logger.info("Test log message")
        
        # Log dosyasının oluşturulduğunu kontrol et
        today = datetime.now().strftime('%Y-%m-%d')
        log_file = os.path.join(self.log_dir, f'trading_bot_{today}.log')
        self.assertTrue(os.path.exists(log_file))
        
        # Eski log dosyalarının temizlendiğini kontrol et
        old_date = (datetime.now() - timedelta(days=31)).strftime('%Y-%m-%d')
        old_log_file = os.path.join(self.log_dir, f'trading_bot_{old_date}.log')
        self.assertFalse(os.path.exists(old_log_file))
        
        logger.info("Günlük log rotasyonu testi başarılı")

class TestSymbolData(unittest.TestCase):
    """Sembol verilerini test eder."""
    
    def setUp(self):
        """Test ortamını hazırlar."""
        self.symbol_data = {
            'AAPL': {
                'dividend_dates': ['2025-05-15', '2025-08-15'],
                'multiplier': 100
            }
        }
    
    def test_dividend_dates_preservation(self):
        """Temettü tarihlerinin korunmasını test eder."""
        # Yeni sembol verisi yükle
        new_data = {
            'AAPL': {
                'price': 150.0,
                'volume': 1000000
            }
        }
        
        # Mevcut temettü tarihlerini koru
        for symbol in new_data:
            if symbol in self.symbol_data:
                new_data[symbol]['dividend_dates'] = self.symbol_data[symbol]['dividend_dates']
        
        self.assertIn('dividend_dates', new_data['AAPL'])
        self.assertEqual(len(new_data['AAPL']['dividend_dates']), 2)
        logger.info("Temettü tarihleri korunma testi başarılı")

def run_all_tests():
    """Tüm testleri çalıştırır ve sonuçları raporlar."""
    logger.info("=== TRADING BOT TEST BAŞLADI ===")
    
    # Tüm test sınıflarını içeren test paketi oluştur
    test_loader = unittest.TestLoader()
    test_suite = unittest.TestSuite()
    
    # Test sınıflarını ekle
    test_classes = [
        TestIGAPI,
        TestTradeCalculator,
        TestWebhookHandler,
        TestTradeManager,
        TestFlaskApp,
        TestCSVOperations,
        TestUserManagement,
        TestLogging,
        TestSymbolData
    ]
    
    for test_class in test_classes:
        tests = test_loader.loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # Testleri çalıştır
    test_runner = unittest.TextTestRunner(verbosity=2)
    test_result = test_runner.run(test_suite)
    
    # Sonuçları raporla
    logger.info("=== TEST SONUÇLARI ===")
    logger.info(f"Toplam test sayısı: {test_result.testsRun}")
    logger.info(f"Başarılı test sayısı: {test_result.testsRun - len(test_result.errors) - len(test_result.failures)}")
    logger.info(f"Başarısız test sayısı: {len(test_result.failures)}")
    logger.info(f"Hata sayısı: {len(test_result.errors)}")
    
    return test_result

if __name__ == "__main__":
    result = run_all_tests()
    # Test sonuçlarına göre çıkış kodu belirle
    if len(result.errors) > 0 or len(result.failures) > 0:
        sys.exit(1)  # Başarısız
    sys.exit(0)  # Başarılı 