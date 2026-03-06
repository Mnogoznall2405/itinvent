import sys
import os

# Set up python path so backend modules can be imported
sys.path.append(os.path.abspath('.'))

from backend.services.network_service import network_service

def delete_target_branch():
    branches = network_service.list_branches("tmn")
    target_branch = None
    for b in branches:
        if "Первомайская 19/21" in b.get("name", ""):
            target_branch = b
            break
            
    if target_branch:
        branch_id = target_branch["id"]
        print(f"Found branch: {target_branch['name']} (ID: {branch_id})")
        network_service.delete_branch(branch_id=branch_id, actor_user_id=1, actor_role='admin')
        print("Branch deleted successfully!")
    else:
        print("Branch 'Первомайская 19/21' not found in city 'tmn'.")
        # try checking other cities if exists, or just print all branches
        print("All branches in 'tmn':", [b.get("name") for b in branches])

if __name__ == "__main__":
    delete_target_branch()
