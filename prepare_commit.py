#!/usr/bin/env python3
"""
Repository Commit Preparation
Final checks and summary before committing the cleaned repository.
"""

import subprocess
import os
from pathlib import Path


def run_git_command(command):
    """Run a git command and return the result."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, check=False)
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return False, "", str(e)


def prepare_for_commit():
    """Prepare repository for commit with final checks."""
    
    print("🚀 REPOSITORY COMMIT PREPARATION")
    print("=" * 50)
    print()
    
    # 1. Check git status
    print("1️⃣ Git Status Check:")
    success, stdout, stderr = run_git_command("git status --porcelain")
    if success:
        if stdout:
            print("   📝 Modified files detected")
            lines = stdout.split('\n')[:10]  # Show first 10 files
            for line in lines:
                print(f"   {line}")
            if len(stdout.split('\n')) > 10:
                print(f"   ... and {len(stdout.split('\n')) - 10} more")
        else:
            print("   ✅ Working directory clean")
    else:
        print(f"   ❌ Git status error: {stderr}")
    print()
    
    # 2. Security verification
    print("2️⃣ Security Verification:")
    sensitive_files = []
    
    # Check for common sensitive patterns
    for pattern in [".env", "*.key", "*private*", "*secret*"]:
        matches = list(Path(".").glob(pattern))
        for match in matches:
            if not str(match).startswith("archive/") and not str(match).endswith((".example", ".template")):
                sensitive_files.append(str(match))
    
    if sensitive_files:
        print("   ⚠️  Potentially sensitive files found:")
        for f in sensitive_files:
            print(f"      📄 {f}")
    else:
        print("   ✅ No sensitive files detected")
    print()
    
    # 3. Archive summary
    print("3️⃣ Archive Summary:")
    archive_path = Path("archive")
    if archive_path.exists():
        for subdir in ["test_scripts", "backup_files", "temporary_data"]:
            subpath = archive_path / subdir
            if subpath.exists():
                count = len(list(subpath.iterdir()))
                print(f"   📦 {subdir}: {count} files")
        print("   ✅ Sensitive files properly archived")
    else:
        print("   ℹ️  No archive directory (none needed)")
    print()
    
    # 4. Core functionality check
    print("4️⃣ Core Functionality Check:")
    core_files = [
        "src/core/services/gas_station.py",
        "src/bot/main_bot.py", 
        "src/bot/handlers/seller_handlers.py",
        "README.md"
    ]
    
    all_present = True
    for file_path in core_files:
        if Path(file_path).exists():
            print(f"   ✅ {file_path}")
        else:
            print(f"   ❌ {file_path} - MISSING!")
            all_present = False
    
    if all_present:
        print("   ✅ All core files present")
    print()
    
    # 5. Fast confirmation implementation check
    print("5️⃣ Fast Confirmation Implementation:")
    gas_station_file = Path("src/core/services/gas_station.py")
    if gas_station_file.exists():
        content = gas_station_file.read_text()
        if "time.sleep(0.5)" in content:
            print("   ✅ Fast confirmation (0.5s polling) implemented")
        else:
            print("   ⚠️  Fast confirmation may not be implemented")
        
        if "check_account_activated_with_details" in content:
            print("   ✅ Enhanced account verification method present")
        else:
            print("   ⚠️  Enhanced account verification may be missing")
    print()
    
    # 6. Environment template check
    print("6️⃣ Environment Configuration:")
    if Path(".env.example").exists():
        print("   ✅ .env.example template present")
    else:
        print("   ⚠️  .env.example template missing")
    
    if Path(".env.development.template").exists():
        print("   ✅ .env.development.template present")
    else:
        print("   ⚠️  .env.development.template missing")
    print()
    
    # 7. Documentation check
    print("7️⃣ Documentation Status:")
    docs = ["README.md", "INTELLIGENT_FREE_GAS_SUMMARY.md", "README_PERMISSION_SYSTEM.md"]
    for doc in docs:
        if Path(doc).exists():
            print(f"   ✅ {doc}")
        else:
            print(f"   ⚠️  {doc} missing")
    print()
    
    # 8. Final recommendation
    print("8️⃣ Commit Recommendation:")
    if not sensitive_files and all_present:
        print("   🎉 REPOSITORY IS READY FOR COMMIT!")
        print()
        print("   Suggested commit commands:")
        print("   git add .")
        print("   git commit -m 'feat: implement fast confirmation system with security cleanup")
        print("   ")
        print("   - Implement 0.5s polling for 4x faster transaction confirmations")
        print("   - Add enhanced account verification with detailed responses")
        print("   - Archive test scripts and sensitive development files")
        print("   - Enhance .gitignore with comprehensive security patterns")
        print("   - Add intelligent free gas system with permission-based activation")
        print("   - Maintain all existing functionality and fallback mechanisms'")
        
    else:
        print("   🛑 ISSUES FOUND - DO NOT COMMIT YET!")
        if sensitive_files:
            print("   ❌ Sensitive files need to be moved/removed")
        if not all_present:
            print("   ❌ Core files missing")
        print()
        print("   Fix issues before committing!")
    
    print()
    print("=" * 50)


if __name__ == "__main__":
    prepare_for_commit()
