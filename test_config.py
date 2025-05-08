import os

# Test ortamı yapılandırması
TEST_CONFIG = {
    'IG_USERNAME': os.getenv('IG_USERNAME', ''),
    'IG_PASSWORD': os.getenv('IG_PASSWORD', ''),
    'IG_API_KEY': os.getenv('IG_API_KEY', ''),
    'IG_DEMO': True,  # Test için demo hesap kullan
    'TEST_USER': 'test_user',
    'TEST_PASSWORD': 'test_password',
    'TEST_ADMIN': 'admin',
    'TEST_ADMIN_PASSWORD': '1234',
    'LOG_DIR': os.path.join(os.path.dirname(__file__), 'logs'),
    'DATA_DIR': os.path.join(os.path.dirname(__file__), 'data')
}

# Test dizinlerini oluştur
for dir_path in [TEST_CONFIG['LOG_DIR'], TEST_CONFIG['DATA_DIR']]:
    if not os.path.exists(dir_path):
        os.makedirs(dir_path) 