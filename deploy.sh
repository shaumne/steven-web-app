#!/bin/bash
# Trading Bot Web Uygulaması Kurulum Scripti

# Hata durumunda işlemi durdur
set -e

echo "==============================================="
echo "   Trading Bot Web Uygulaması Kurulum Scripti  "
echo "==============================================="

# Kullanıcıdan gerekli bilgileri al
read -p "Domain adınız (örn: www.grangemail.com): " DOMAIN
read -p "Sunucu IP adresiniz: " SERVER_IP
read -p "IG Markets API kullanıcı adınız: " IG_USERNAME
read -s -p "IG Markets API şifreniz: " IG_PASSWORD
echo ""
read -s -p "IG Markets API API anahtarınız: " IG_API_KEY
echo ""
# GitHub repo URL'sini doğrudan tanımla
REPO_URL="https://github.com/shaumne/steven-web-app.git"
read -p "Email adresiniz (SSL sertifikası için): " EMAIL

# Kullanıcı adını belirle
USERNAME=$(whoami)
APP_DIR="/home/$USERNAME/trading_bot"
ENV_FILE="$APP_DIR/.env"

# Sistem güncellemesi
echo "Sistem güncelleniyor..."
sudo apt update && sudo apt upgrade -y

# Gerekli paketleri yükle
echo "Gerekli paketler yükleniyor..."
sudo apt install -y python3 python3-pip python3-venv nginx git certbot python3-certbot-nginx ufw supervisor

# Firewall yapılandırması
echo "Firewall yapılandırılıyor..."
sudo ufw allow 'Nginx Full'
sudo ufw allow ssh
sudo ufw --force enable

# Uygulama klasörü oluşturma
echo "Uygulama klasörü oluşturuluyor..."
mkdir -p $APP_DIR

# Eğer bir repo URL'si verilmişse git clone yap
if [ ! -z "$REPO_URL" ]; then
    echo "Github repo'dan kodu klonlama..."
    git clone $REPO_URL $APP_DIR
else
    echo "Uygulama kodunun manuel olarak yüklenmesi gerekecek."
    mkdir -p $APP_DIR/trading_bot
    touch $APP_DIR/app.py
    touch $APP_DIR/run.py
    touch $APP_DIR/requirements.txt
    echo "Flask==2.0.1
requests==2.26.0
pandas==1.3.3
python-dotenv==0.19.0" > $APP_DIR/requirements.txt
fi

# Python sanal ortamı oluşturma
echo "Python sanal ortamı oluşturuluyor..."
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate

# Bağımlılıkları yükleme
echo "Python bağımlılıkları yükleniyor..."
pip install -U pip
pip install -r requirements.txt
pip install gunicorn

# .env dosyasını oluştur
echo "Çevresel değişkenler yapılandırılıyor..."
cat > $ENV_FILE << EOL
IG_USERNAME=$IG_USERNAME
IG_PASSWORD=$IG_PASSWORD
IG_API_KEY=$IG_API_KEY
IG_DEMO=0
CSV_FILE_PATH=$APP_DIR/ticker_data.csv
LOG_LEVEL=INFO
FLASK_ENV=production
EOL

# Gunicorn servis dosyası
echo "Gunicorn servis dosyası oluşturuluyor..."
cat > /tmp/trading-bot.service << EOL
[Unit]
Description=Trading Bot Gunicorn Service
After=network.target

[Service]
User=$USERNAME
Group=www-data
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/venv/bin/gunicorn --workers 3 --bind unix:$APP_DIR/trading_bot.sock -m 007 run:app

[Install]
WantedBy=multi-user.target
EOL

sudo mv /tmp/trading-bot.service /etc/systemd/system/

# Nginx konfigurasyonu
echo "Nginx yapılandırılıyor..."
cat > /tmp/trading-bot.nginx << EOL
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        include proxy_params;
        proxy_pass http://unix:$APP_DIR/trading_bot.sock;
        proxy_read_timeout 180s;
    }

    location /webhook {
        include proxy_params;
        proxy_pass http://unix:$APP_DIR/trading_bot.sock;
        proxy_read_timeout 180s;
    }
}
EOL

sudo mv /tmp/trading-bot.nginx /etc/nginx/sites-available/trading-bot
sudo ln -s /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/

# Nginx test
sudo nginx -t

# Servisleri başlat
echo "Servisleri başlatma..."
sudo systemctl daemon-reload
sudo systemctl start trading-bot
sudo systemctl enable trading-bot
sudo systemctl restart nginx

# SSL sertifikası kurma
echo "SSL sertifikası alınıyor..."
sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email $EMAIL

# Monitoring kurulumu (basit)
echo "Basit monitoring ayarlanıyor..."
cat > /tmp/monitor-trading-bot.sh << EOL
#!/bin/bash
# Trading Bot monitoring script

SERVICE="trading-bot"
LOG_FILE="/var/log/trading-bot-monitor.log"

if ! systemctl is-active --quiet \$SERVICE; then
    echo "\$(date): \$SERVICE is down, restarting..." >> \$LOG_FILE
    systemctl restart \$SERVICE
    echo "\$(date): \$SERVICE restart attempted" >> \$LOG_FILE
fi
EOL

sudo mv /tmp/monitor-trading-bot.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/monitor-trading-bot.sh

# Cron job kurma
(crontab -l 2>/dev/null; echo "*/5 * * * * /usr/local/bin/monitor-trading-bot.sh") | crontab -

echo ""
echo "==============================================="
echo "   Trading Bot Web Uygulaması Kurulumu Tamamlandı!"
echo "==============================================="
echo ""
echo "Uygulamanız şu adreste çalışıyor: https://$DOMAIN"
echo ""
echo "Servis durumunu kontrol etme: sudo systemctl status trading-bot"
echo "Nginx durumunu kontrol etme: sudo systemctl status nginx"
echo "Uygulama loglarını görüntüleme: sudo journalctl -u trading-bot"
echo ""
echo "Bu komutları şu anda değil, sunucunuza giriş yaptıktan sonra çalıştırın."
echo "==============================================="