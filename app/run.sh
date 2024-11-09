echo -e "#!/usr/bin/env bash\n/usr/bin/shellinaboxd -t -s /:LOGIN" > /home/choreouser/1.sh
chmod +x /home/choreouser/1.sh
pm2 start /home/choreouser/1.sh
python3 /home/choreouser/12.py
