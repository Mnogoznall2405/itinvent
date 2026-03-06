from ldap3 import Server, Connection, ALL, SUBTREE
import os

# ==========================================
# КОНФИГУРАЦИЯ / CONFIGURATION
# ==========================================
# 1. Адрес контроллера домена 
LDAP_SERVER = "10.103.0.150" 

# 2. Учетные данные для подключения
LDAP_USER = "kozlovskii.me@zsgp.corp"
LDAP_PASSWORD = "FH2fj#$23d1"

# 3. Корень поиска (Base DN)
LDAP_BASE_DN = "dc=zsgp,dc=corp"

# 4. Имя компьютера для поиска
# Например: "TMN-IT-0009"
TARGET_PC_NAME = "TMN-IT-0009"
# ==========================================

def find_users_by_computer(pc_name):
    print(f"[*] Подключение к серверу {LDAP_SERVER}...")
    server = Server(LDAP_SERVER, get_info=ALL)
    
    try:
        conn = Connection(
            server, 
            user=LDAP_USER, 
            password=LDAP_PASSWORD, 
            auto_bind=True
        )
        print("[+] Авторизация пройдена.")
    except Exception as e:
        return f"[-] Ошибка авторизации: {e}"

    # Фильтр поиска: ищем всех людей, у которых в заметках (info) упоминается имя ПК
    # Формат: * ИМЯ_ПК * (звездочки позволяют найти текст внутри строки)
    search_filter = f"(&(objectCategory=person)(objectClass=user)(info=*{pc_name}*))"
    
    attributes = ['displayName', 'sAMAccountName', 'info', 'telephoneNumber']
    
    print(f"[*] Поиск пользователей, входивших на {pc_name}...")
    
    try:
        conn.search(
            search_base=LDAP_BASE_DN, 
            search_filter=search_filter, 
            attributes=attributes, 
            search_scope=SUBTREE
        )
        
        if not conn.entries:
            conn.unbind()
            return f"[-] Пользователи для ПК '{pc_name}' не найдены."
            
        output = []
        output.append("=" * 50)
        output.append(f"РЕЗУЛЬТАТЫ ДЛЯ КОМПЬЮТЕРА: {pc_name.upper()}")
        output.append("-" * 50)
        
        for entry in conn.entries:
            output.append(f"ФИО:      {entry.displayName.value}")
            output.append(f"Логин:    {entry.sAMAccountName.value}")
            output.append(f"Заметка:  {entry.info.value}")
            output.append(f"Телефон:  {entry.telephoneNumber.value if 'telephoneNumber' in entry else '-'}")
            output.append("-" * 50)
        
        output.append(f"Всего найдено: {len(conn.entries)}")
        output.append("=" * 50)
        
        conn.unbind()
        return "\n".join(output)
        
    except Exception as e:
        if 'conn' in locals(): conn.unbind()
        return f"[-] Ошибка при поиске: {e}"

if __name__ == "__main__":
    # Если хотите искать другой компьютер, можно ввести его вручную:
    # pc_to_find = input("Введите имя ПК (например, TMN-IT-0009): ").strip()
    # if not pc_to_find: pc_to_find = TARGET_PC_NAME
    
    result = find_users_by_computer(TARGET_PC_NAME)
    print("\n" + result)
    input("\nНажмите Enter для выхода...")
