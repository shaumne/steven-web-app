#!/bin/bash

# Steven Trading Bot - AWS EC2 Ubuntu Tam Kurulum ve Deploy Scripti
# Kullanım: sudo bash deploy_aws.sh

# Renkli çıktı için
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Log fonksiyonu
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] HATA: $1${NC}"
    exit 1
}

warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] UYARI: $1${NC}"
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] BİLGİ: $1${NC}"
}

# Root olarak çalıştırılıp çalıştırılmadığını kontrol et
if [ "$EUID" -ne 0 ]; then
    error "Bu script root olarak çalıştırılmalıdır. 'sudo bash deploy_aws.sh' şeklinde çalıştırın."
fi

# Domain adı ve diğer sabitler
DOMAIN="grangemail.com"
APP_DIR="/opt/steven-trading-bot"
GITHUB_REPO="https://github.com/shaumne/steven-web-app.git"
SERVICE_NAME="steven-bot"
NGINX_CONF="/etc/nginx/sites-available/$DOMAIN"

log "============================================="
log "Steven Trading Bot AWS Kurulum Scripti"
log "Domain: $DOMAIN"
log "============================================="

# 1. Sistem Güncellemesi
log "1. Sistem güncelleniyor..."
apt update && apt upgrade -y || error "Sistem güncellenemedi"

# 2. Gerekli paketleri yükle
log "2. Gerekli sistem paketleri yükleniyor..."
apt install -y git build-essential libssl-dev libffi-dev python3-dev nginx certbot python3-certbot-nginx supervisor || error "Paketler yüklenemedi"

# Python 3.10 kurulumu
log "2.1 Python 3.10 kurulumu yapılıyor..."
apt install -y software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt update
apt install -y python3.10 python3.10-venv python3.10-dev || error "Python 3.10 yüklenemedi"

# 3. Git deposunu klonla
log "3. GitHub repo klonlanıyor..."
if [ -d "$APP_DIR" ]; then
    log "   Mevcut repo güncelleniyor..."
    cd $APP_DIR
    git pull || error "Git pull başarısız oldu"
else
    log "   Repo klonlanıyor..."
    git clone $GITHUB_REPO $APP_DIR || error "Git repo klonlanamadı"
    cd $APP_DIR
fi

# 4. Python sanal ortamı oluştur
log "4. Python sanal ortamı oluşturuluyor..."
if [ ! -d "$APP_DIR/venv" ]; then
    python3.10 -m venv $APP_DIR/venv || error "Python sanal ortamı oluşturulamadı"
fi

# 5. Python bağımlılıklarını yükle
log "5. Python bağımlılıkları yükleniyor..."
$APP_DIR/venv/bin/pip install --upgrade pip setuptools wheel || error "Pip ve gerekli araçlar güncellenemedi"

# Önce numpy ve temel bileşenleri kur
log "   Temel bağımlılıkları yükleniyor..."
$APP_DIR/venv/bin/pip install -v numpy || warning "Numpy yüklenirken sorun oluştu, devam ediliyor"

# Sonra diğer tüm bağımlılıkları yükle
log "   Tüm bağımlılıkları yükleniyor..."
$APP_DIR/venv/bin/pip install -v -r $APP_DIR/requirements.txt || error "Requirements yüklenemedi"
$APP_DIR/venv/bin/pip install -v gunicorn || error "Gunicorn yüklenemedi"

# 6. Çevre değişkenleri yapılandır
log "6. Çevre değişkenleri yapılandırılıyor..."
if [ ! -f "$APP_DIR/.env" ]; then
    warning "   .env dosyası bulunamadı. Örnek .env dosyası oluşturuluyor..."
    
    # IG Markets bilgilerini kullanıcıdan al
    echo "IG Markets API bilgilerini girin:"
    read -p "IG Markets kullanıcı adı: " IG_USERNAME
    read -s -p "IG Markets şifre: " IG_PASSWORD
    echo ""
    read -s -p "IG Markets API anahtarı: " IG_API_KEY
    echo ""
    read -p "IG Markets hesap tipi (DEMO veya LIVE): " IG_ACCOUNT_TYPE
    
    # IG_ACCOUNT_TYPE doğrulama ve düzeltme
    if [[ "$IG_ACCOUNT_TYPE" == "1" || "$IG_ACCOUNT_TYPE" == "DEMO" ]]; then
        IG_ACCOUNT_TYPE="DEMO"
    elif [[ "$IG_ACCOUNT_TYPE" == "0" || "$IG_ACCOUNT_TYPE" == "LIVE" ]]; then
        IG_ACCOUNT_TYPE="LIVE"
    else
        warning "Geçersiz hesap tipi, varsayılan olarak DEMO kullanılıyor"
        IG_ACCOUNT_TYPE="DEMO"
    fi
    
    # SSL için email adresi
    read -p "SSL sertifikası için email adresi: " SSL_EMAIL
    
    cat > $APP_DIR/.env << EOF
IG_USERNAME=$IG_USERNAME
IG_PASSWORD=$IG_PASSWORD
IG_API_KEY=$IG_API_KEY
IG_ACCOUNT_TYPE=$IG_ACCOUNT_TYPE
CSV_FILE_PATH=ticker_data.csv
FLASK_ENV=production
PORT=5000
SSL_EMAIL=$SSL_EMAIL
EOF
    log "   .env dosyası oluşturuldu."
else
    log "   Mevcut .env dosyası kullanılacak."
fi

# 7. İzinleri ayarla
log "7. Dosya izinleri ayarlanıyor..."
chown -R www-data:www-data $APP_DIR
chmod -R 755 $APP_DIR

# 8. Supervisor yapılandırması
log "8. Supervisor yapılandırılıyor..."
cat > /etc/supervisor/conf.d/$SERVICE_NAME.conf << EOF
[program:$SERVICE_NAME]
directory=$APP_DIR
command=$APP_DIR/venv/bin/gunicorn app:app -w 4 -b 127.0.0.1:5000
user=www-data
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stderr_logfile=/var/log/$SERVICE_NAME.err.log
stdout_logfile=/var/log/$SERVICE_NAME.out.log
EOF

# 9. Supervisor'ı yenile ve servisi başlat
log "9. Supervisor servisi yeniden başlatılıyor..."
supervisorctl reread || error "Supervisor reread başarısız oldu"
supervisorctl update || error "Supervisor update başarısız oldu"
supervisorctl restart $SERVICE_NAME || warning "Servis yeniden başlatılamadı, ilk kez başlatılacak"

# 10. Nginx yapılandırması
log "10. Nginx yapılandırılıyor..."
cat > $NGINX_CONF << EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 90;
    }

    location /static {
        alias $APP_DIR/static;
        expires 30d;
    }

    location /webhook {
        proxy_pass http://127.0.0.1:5000/webhook;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
    }
}
EOF

# 11. Nginx yapılandırmasını etkinleştir
log "11. Nginx yapılandırması etkinleştiriliyor..."
ln -sf $NGINX_CONF /etc/nginx/sites-enabled/ || error "Nginx yapılandırması etkinleştirilemedi"
nginx -t || error "Nginx konfigürasyon testi başarısız oldu"
systemctl restart nginx || error "Nginx yeniden başlatılamadı"

# 12. SSL sertifikası al
log "12. SSL sertifikası için DNS kontrolü yapılıyor..."
IP_ADDRESS=$(curl -s https://api.ipify.org)
log "Sunucu IP adresi: $IP_ADDRESS"
log "SSL sertifikası almak için domainlerinizin ($DOMAIN ve www.$DOMAIN) DNS A kayıtlarının"
log "bu sunucunun IP adresine ($IP_ADDRESS) yönlendirilmiş olması gerekiyor."
log ""
log "SSL sertifikası almadan önce DNS kayıtlarınızı kontrol edin."
log "DNS kayıtları ayarlandıktan sonra genellikle yayılması 15-30 dakika sürebilir."

read -p "SSL sertifikası kurulumuna şimdi devam etmek istiyor musunuz? (e/h): " SSL_CONTINUE

if [[ "$SSL_CONTINUE" == "e" || "$SSL_CONTINUE" == "E" ]]; then
    # .env dosyasından SSL e-posta adresini al
    if [ -f "$APP_DIR/.env" ] && grep -q "SSL_EMAIL" "$APP_DIR/.env"; then
        SSL_EMAIL=$(grep "SSL_EMAIL" "$APP_DIR/.env" | cut -d'=' -f2)
        log "SSL için kayıtlı e-posta adresi kullanılıyor: $SSL_EMAIL"
    else
        read -p "SSL sertifikası için email adresi: " SSL_EMAIL
    fi
    
    if certbot --nginx -d $DOMAIN -d www.$DOMAIN --non-interactive --agree-tos --email $SSL_EMAIL --redirect; then
        log "SSL sertifikası başarıyla kuruldu!"
        
        # SSL konfigürasyonunu güçlendir
        log "12.1 SSL güvenlik ayarları yapılandırılıyor..."
        cat > /etc/nginx/conf.d/ssl-params.conf << EOF
ssl_session_timeout 1d;
ssl_session_cache shared:SSL:10m;
ssl_session_tickets off;
ssl_stapling on;
ssl_stapling_verify on;
resolver 8.8.8.8 8.8.4.4 valid=300s;
resolver_timeout 5s;
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";
add_header X-Frame-Options DENY;
add_header X-Content-Type-Options nosniff;
add_header X-XSS-Protection "1; mode=block";
EOF

        # HTTPS yapılandırmasını test et ve Nginx'i yeniden başlat
        nginx -t && systemctl restart nginx
        
        # Cron job ekleyin (sertifika yenileme için)
        log "14. SSL sertifika yenileme için cron job ekleniyor..."
        (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet") | crontab -
    else
        warning "SSL sertifikası kurulumu başarısız oldu."
        log "DNS ayarlarınızı kontrol ettikten sonra aşağıdaki komutu kullanarak tekrar deneyebilirsiniz:"
        log "sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN"
    fi
else
    log "SSL sertifikası kurulumu atlandı. Daha sonra manuel olarak kurabilirsiniz:"
    log "sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN"
fi

# 13. Firewall ayarları
log "13. Firewall ayarları yapılıyor..."
ufw allow 'Nginx Full' || warning "UFW Nginx Full rule eklenemedi"
ufw allow ssh || warning "UFW SSH rule eklenemedi"
ufw --force enable || warning "UFW etkinleştirilemedi"

# 14. Cron işlemleri
if [[ "$SSL_CONTINUE" != "e" && "$SSL_CONTINUE" != "E" ]]; then
    log "14. SSL kurulmadığı için SSL yenileme cron job'ı atlandı"
fi

# 15. Son kontroller
log "15. Servis durumu kontrol ediliyor..."
supervisorctl status $SERVICE_NAME || warning "Servis durumu alınamadı"

# Nginx ve uygulamanın erişilebilir olduğunu kontrol et
log "16. Nginx ve uygulama erişimi kontrol ediliyor..."
if curl -s -I http://localhost | grep -q "200 OK"; then
    log "Nginx çalışıyor ve localhost üzerinden erişilebilir"
else
    warning "Nginx localhost üzerinden erişilemiyor. Nginx durumunu kontrol edin: systemctl status nginx"
fi

log "============================================="
log "KURULUM TAMAMLANDI!"
if [[ "$SSL_CONTINUE" == "e" || "$SSL_CONTINUE" == "E" ]]; then
    if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
        log "Uygulamanız güvenli bir şekilde şu adreste çalışıyor:"
        log "https://$DOMAIN"
    else
        log "Uygulamanız şu adreste çalışıyor:"
        log "http://$DOMAIN"
        log "(SSL sertifikası kurulumu başarısız oldu, DNS ayarlarından sonra tekrar deneyin)"
    fi
else
    log "Uygulamanız şu adreste çalışıyor:"
    log "http://$DOMAIN"
    log "(SSL kurulumu yapılmadı)"
fi
log "============================================="

# Kullanışlı komutları göster
log "YARDIMCI KOMUTLAR:"
log "Logları görmek için: tail -f /var/log/$SERVICE_NAME.out.log"
log "Hata logları için: tail -f /var/log/$SERVICE_NAME.err.log"
log "Servisi yeniden başlatmak için: supervisorctl restart $SERVICE_NAME"
log "Nginx'i yeniden başlatmak için: sudo systemctl restart nginx"
log "============================================="

# DNS kontrolü
IP_ADDRESS=$(curl -s https://api.ipify.org)
log "ÖNEMLİ DNS KONTROLÜ:"
log "Sunucu IP adresi: $IP_ADDRESS"
log "Lütfen DNS A kaydınızın '$DOMAIN' ve 'www.$DOMAIN' için $IP_ADDRESS adresine"
log "yönlendirildiğinden emin olun."

# SSL kurulumu sonrası talimatlar
if [[ "$SSL_CONTINUE" != "e" && "$SSL_CONTINUE" != "E" ]]; then
    log "SSL KURULUMU TAMAMLANMADI."
    log "DNS ayarları yapıldıktan sonra SSL kurulumu için:"
    log "sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN"
    log "komutu ile manuel olarak SSL kurulumunu yapabilirsiniz."
elif [ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    log "SSL KURULUMU BAŞARISIZ OLDU."
    log "DNS ayarları yapıldıktan sonra SSL kurulumu için:"
    log "sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN"
    log "komutu ile manuel olarak SSL kurulumunu yapabilirsiniz."
fi
log "============================================="

# En son echo ile kullanım talimatlarını göster
echo ""
echo "Bu sunucuya SSH ile bağlandığınızda şu komutlarla uygulamayı yönetebilirsiniz:"
echo ""
echo "  - sudo supervisorctl status $SERVICE_NAME       # Servis durumunu göster"
echo "  - sudo supervisorctl restart $SERVICE_NAME      # Servisi yeniden başlat"
echo "  - sudo supervisorctl stop $SERVICE_NAME         # Servisi durdur"
echo "  - sudo supervisorctl start $SERVICE_NAME        # Servisi başlat"
echo "  - sudo tail -f /var/log/$SERVICE_NAME.out.log   # Uygulama loglarını izle"
echo "  - sudo tail -f /var/log/$SERVICE_NAME.err.log   # Hata loglarını izle"
echo "  - sudo certbot renew --dry-run                  # SSL sertifika yenilemeyi test et"
echo ""
echo "Uygulamaya tarayıcıdan erişmek için: http://$DOMAIN"
echo "DNS ayarları yapıldıktan sonra SSL kurulumu için: sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN"
echo "============================================="