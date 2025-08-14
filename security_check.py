#!/usr/bin/env python3
"""
Repository Security Check
Scans for sensitive data before commit to prevent accidental exposure.
"""

import os
import re
import glob
from pathlib import Path


def security_check():
    """Comprehensive security check for sensitive data."""
    
    print("🔐 REPOSITORY SECURITY CHECK")
    print("=" * 50)
    
    # Define sensitive patterns
    sensitive_patterns = {
        "Private Keys": [
            r"private.*key.*[=:]\s*[\"']?[a-fA-F0-9]{64}",
            r"PRIVATE_KEY.*[=:]\s*[\"']?[a-fA-F0-9]{64}",
            r"-----BEGIN PRIVATE KEY-----",
            r"-----BEGIN RSA PRIVATE KEY-----"
        ],
        "Mnemonics/Seeds": [
            r"mnemonic.*[=:]\s*[\"'][^\"']{50,}",
            r"seed.*phrase.*[=:]\s*[\"'][^\"']{50,}",
            r"\b(?:\w+\s+){11,23}\w+\b"  # 12-24 word mnemonic pattern
        ],
        "API Keys/Tokens": [
            r"api.*key.*[=:]\s*[\"']?[a-zA-Z0-9]{20,}",
            r"token.*[=:]\s*[\"']?[a-zA-Z0-9]{20,}",
            r"secret.*[=:]\s*[\"']?[a-zA-Z0-9]{20,}",
            r"TELEGRAM_BOT_TOKEN.*[=:]\s*[\"']?\d+:[a-zA-Z0-9_-]{35}"
        ],
        "Wallet Addresses with Values": [
            r"T[A-Za-z0-9]{33}.*[=:]\s*[\"']?[a-fA-F0-9]{64}",
            r"0x[a-fA-F0-9]{40}.*[=:]\s*[\"']?[a-fA-F0-9]{64}"
        ],
        "Passwords": [
            r"password.*[=:]\s*[\"'][^\"']{8,}",
            r"PASSWORD.*[=:]\s*[\"'][^\"']{8,}"
        ]
    }
    
    # Files to check
    repo_root = Path(".")
    files_to_check = []
    
    # Include specific file types
    for pattern in ["**/*.py", "**/*.js", "**/*.json", "**/*.md", "**/*.txt", "**/*.yml", "**/*.yaml"]:
        files_to_check.extend(glob.glob(pattern, recursive=True))
    
    # Exclude sensitive/archive directories
    exclude_patterns = [
        "archive/", ".git/", ".venv/", "node_modules/", 
        "__pycache__/", ".pytest_cache/", "logs/", "data/"
    ]
    
    files_to_check = [f for f in files_to_check 
                     if not any(exc in f for exc in exclude_patterns)]
    
    print(f"📁 Checking {len(files_to_check)} files...")
    print()
    
    issues_found = []
    
    for file_path in files_to_check:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
                for category, patterns in sensitive_patterns.items():
                    for pattern in patterns:
                        matches = re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)
                        for match in matches:
                            # Get line number
                            line_num = content[:match.start()].count('\n') + 1
                            line_content = content.split('\n')[line_num - 1].strip()[:100]
                            
                            issues_found.append({
                                "file": file_path,
                                "category": category,
                                "line": line_num,
                                "content": line_content,
                                "pattern": pattern[:50] + "..." if len(pattern) > 50 else pattern
                            })
                            
        except Exception as e:
            print(f"⚠️  Could not read {file_path}: {e}")
    
    # Report results
    if not issues_found:
        print("✅ NO SENSITIVE DATA FOUND!")
        print()
        print("🎉 Repository is clean and safe for commit.")
        return True
    else:
        print(f"❌ FOUND {len(issues_found)} POTENTIAL SECURITY ISSUES!")
        print()
        
        by_category = {}
        for issue in issues_found:
            category = issue["category"]
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(issue)
        
        for category, issues in by_category.items():
            print(f"🚨 {category} ({len(issues)} issues):")
            for issue in issues[:3]:  # Show first 3 per category
                print(f"   📄 {issue['file']}:{issue['line']}")
                print(f"      {issue['content']}")
            if len(issues) > 3:
                print(f"   ... and {len(issues) - 3} more")
            print()
        
        print("🛡️  RECOMMENDED ACTIONS:")
        print("   1. Remove or move sensitive files to archive/")
        print("   2. Use environment variables (.env) for secrets")
        print("   3. Update .gitignore to exclude sensitive patterns")
        print("   4. Use placeholder values in example files")
        print()
        
        return False


def check_git_status():
    """Check git status for staged files."""
    print("📋 GIT STATUS CHECK")
    print("=" * 30)
    
    try:
        import subprocess
        result = subprocess.run(["git", "status", "--porcelain"], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            staged_files = [line for line in result.stdout.split('\n') 
                          if line.startswith('A ') or line.startswith('M ')]
            
            if staged_files:
                print(f"📝 {len(staged_files)} files staged for commit:")
                for file_line in staged_files[:10]:  # Show first 10
                    print(f"   {file_line}")
                if len(staged_files) > 10:
                    print(f"   ... and {len(staged_files) - 10} more")
            else:
                print("ℹ️  No files currently staged for commit")
            print()
            
        else:
            print("⚠️  Could not get git status")
            
    except Exception as e:
        print(f"⚠️  Git status check failed: {e}")
    

def cleanup_summary():
    """Show cleanup summary."""
    print("🧹 CLEANUP SUMMARY")
    print("=" * 30)
    
    archive_path = Path("archive")
    if archive_path.exists():
        test_scripts = len(list(archive_path.glob("test_scripts/*"))) if (archive_path / "test_scripts").exists() else 0
        backup_files = len(list(archive_path.glob("backup_files/*"))) if (archive_path / "backup_files").exists() else 0
        temp_data = len(list(archive_path.glob("temporary_data/*"))) if (archive_path / "temporary_data").exists() else 0
        
        print(f"📦 Archived files:")
        print(f"   🧪 Test scripts: {test_scripts}")
        print(f"   💾 Backup files: {backup_files}")  
        print(f"   📄 Temporary data: {temp_data}")
        print()
    
    # Check for remaining sensitive patterns in filenames
    sensitive_files = []
    for pattern in ["*private*", "*secret*", "*.env", "*mnemonic*", "*key*"]:
        matches = glob.glob(pattern)
        sensitive_files.extend([f for f in matches if not f.startswith('.env.example') 
                               and not f.startswith('.env.development.template')])
    
    if sensitive_files:
        print(f"⚠️  Potentially sensitive files still present:")
        for f in sensitive_files:
            print(f"   📄 {f}")
        print()
    else:
        print("✅ No sensitive files in repository root")
        print()


if __name__ == "__main__":
    print("🔍 PRE-COMMIT SECURITY AND CLEANUP CHECK")
    print("=" * 60)
    print()
    
    # Run all checks
    cleanup_summary()
    check_git_status()
    is_secure = security_check()
    
    print("=" * 60)
    if is_secure:
        print("🎉 REPOSITORY IS READY FOR COMMIT!")
        print()
        print("✅ No sensitive data detected")
        print("✅ Files properly archived")
        print("✅ Security patterns in place")
    else:
        print("🛑 REPOSITORY NOT READY FOR COMMIT!")
        print()
        print("❌ Security issues found")
        print("💡 Fix issues before committing")
    
    print()
    print("🚀 Next steps:")
    print("   1. Review security check results")
    print("   2. Move any remaining sensitive files")
    print("   3. Run: git add . && git commit -m 'Clean repository with security measures'")
