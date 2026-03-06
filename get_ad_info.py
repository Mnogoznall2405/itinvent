from ldap3 import Server, Connection, ALL, SUBTREE
import os

# ==========================================
# КОНФИГУРАЦИЯ / CONFIGURATION
# ==========================================
# 1. Адрес контроллера домена 
# Попробуйте "zsgp.corp" или IP (например, "10.103.0.1")
LDAP_SERVER = "10.103.0.150" 

# 2. Учетные данные для подключения
# Можно использовать формат "user@domain.com" или "DOMAIN\user"
LDAP_USER = "kozlovskii.me@zsgp.corp"
LDAP_PASSWORD = "FH2fj#$23d1"

# 3. Корень поиска (Base DN)
LDAP_BASE_DN = "dc=zsgp,dc=corp"

# 4. ФИО пользователя для поиска в AD
TARGET_DISPLAY_NAME = "Козловский Максим Евгеньевич"
# ==========================================

import re

def get_ad_user_info(full_name):
    print(f"[*] Подключение к серверу {LDAP_SERVER}...")
    server = Server(LDAP_SERVER, get_info=ALL)
    
    try:
        conn = Connection(
            server, 
            user=LDAP_USER, 
            password=LDAP_PASSWORD, 
            auto_bind=True
        )
        print("[+] Авторизация в Active Directory пройдена успешно.")
    except Exception as e:
        return f"[-] Ошибка авторизации: {e}"

    search_filter = f"(&(objectCategory=person)(objectClass=user)(displayName={full_name}))"
    attributes = ['displayName', 'telephoneNumber', 'mobile', 'info', 'description']
    
    print(f"[*] Ищем пользователя: {full_name}...")
    
    try:
        conn.search(
            search_base=LDAP_BASE_DN, 
            search_filter=search_filter, 
            attributes=attributes, 
            search_scope=SUBTREE
        )
        
        if not conn.entries:
            conn.unbind()
            return f"[-] Пользователь '{full_name}' не найден."
            
        entry = conn.entries[0]
        notes = str(entry.info.value) if 'info' in entry and entry.info.value else ""
        
        # Регулярное выражение для поиска имени компьютера после символа @
        # Ожидаем формат: ... @ ИМЯ_КОМПЬЮТЕРА ...
        computer_name = "не найдено"
        if notes:
            match = re.search(r'@\s*([A-Za-z0-9-]+)', notes)
            if match:
                computer_name = match.group(1)
        
        output = []
        output.append("=" * 40)
        output.append(f"Данные из AD для: {entry.displayName.value}")
        output.append("-" * 40)
        output.append(f"ИМЯ КОМПЬЮТЕРА: {computer_name.upper()}")
        output.append("-" * 40)
        output.append(f"Рабочий телефон: {entry.telephoneNumber.value if 'telephoneNumber' in entry else 'не указан'}")
        output.append(f"Заметки (полностью): {notes if notes else 'пусто'}")
        output.append("=" * 40)
        
        conn.unbind()
        return "\n".join(output)
        
    except Exception as e:
        if 'conn' in locals(): conn.unbind()
        return f"[-] Ошибка при поиске данных: {e}"

if __name__ == "__main__":
    result = get_ad_user_info(TARGET_DISPLAY_NAME)
    print("\nРЕЗУЛЬТАТ:")
    print(result)
    print("\nНажмите Enter, чтобы закрыть окно...")
    input()
