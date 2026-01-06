from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext
import time
import re
import random
import string
import json
import requests


class GitHubRegister:
    def __init__(self, email_domain, api_base="http://127.0.0.1:14000", headless=True, proxy=None, proxy_list=None, target_repo="sribdcn/PersonalExam"):
        self.email_domain = email_domain
        self.api_base = api_base
        self.headless = headless
        self.proxy = proxy
        self.proxy_list = proxy_list or []
        self.current_proxy_index = 0
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.blocked_count = 0
        self.target_repo = target_repo

    def init_driver(self):
        print("[OK] Using Playwright (anti-fingerprint enabled)")
        print(f"[DEBUG] init_driver: headless={self.headless}, proxy={self.proxy}")
        
        print("[DEBUG] init_driver: Starting Playwright...")
        self.playwright = sync_playwright().start()
        
        # 浏览器启动参数
        launch_options = {
            'headless': self.headless,
            'args': [
                '--lang=en-US',
                '--disable-blink-features=AutomationControlled',
            ]
        }
        print(f"[DEBUG] init_driver: Launch options: {launch_options}")
        
        # 代理设置
        proxy_config = None
        if self.proxy:
            if self.proxy.startswith('http://') or self.proxy.startswith('https://'):
                proxy_url = self.proxy
            else:
                proxy_url = f'http://{self.proxy}'
            proxy_config = {'server': proxy_url}
            print(f"[DEBUG] init_driver: Using proxy: {proxy_config}")
        
        # 启动浏览器
        print("[DEBUG] init_driver: Launching browser...")
        self.browser = self.playwright.chromium.launch(**launch_options)
        print("[DEBUG] init_driver: Browser launched")
        
        # 创建上下文（支持反检测）
        context_options = {
            'viewport': {'width': 1280, 'height': 720},
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'locale': 'en-US',
            'timezone_id': 'America/New_York',
        }
        
        if proxy_config:
            context_options['proxy'] = proxy_config
        
        # 注入反检测脚本
        context_options['java_script_enabled'] = True
        
        print("[DEBUG] init_driver: Creating browser context...")
        self.context = self.browser.new_context(**context_options)
        print("[DEBUG] init_driver: Context created")
        
        # 注入反指纹脚本
        print("[DEBUG] init_driver: Injecting anti-fingerprint scripts...")
        self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
        """)
        
        print("[DEBUG] init_driver: Creating new page...")
        self.page = self.context.new_page()
        print("[OK] Browser initialized successfully")

    def close_driver(self):
        if self.page:
            self.page.close()
            self.page = None
        if self.context:
            self.context.close()
            self.context = None
        if self.browser:
            self.browser.close()
            self.browser = None
        if self.playwright:
            self.playwright.stop()
            self.playwright = None

    def detect_anti_bot(self):
        """检测是否触发反爬虫机制（已禁用所有检测）"""
        if not self.page:
            print("[DEBUG] detect_anti_bot: No page available")
            return False, "No page"
        
        try:
            print("[DEBUG] detect_anti_bot: All detection disabled, returning False")
            # 所有检测逻辑已禁用
            return False, None
            
        except Exception as e:
            print(f"[DEBUG] detect_anti_bot: Error - {e}")
            return False, f"Detection error: {e}"

    def handle_anti_bot(self, reason):
        """处理反爬虫触发"""
        self.blocked_count += 1
        print(f"[WARN] Anti-bot detected: {reason}")
        print(f"   Blocked count: {self.blocked_count}")
        
        wait_time = min(60 * self.blocked_count, 300)
        print(f"   Waiting {wait_time}s before retry...")
        time.sleep(wait_time)
        
        if self.proxy_list:
            self.rotate_proxy()
            print(f"   Switched to new proxy")
        
        self.close_driver()
        time.sleep(random.uniform(2, 5))
        self.init_driver()
        print(f"   Browser reinitialized")

    def rotate_proxy(self):
        """轮换代理"""
        if not self.proxy_list:
            return
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxy_list)
        self.proxy = self.proxy_list[self.current_proxy_index]
        print(f"   Using proxy: {self.proxy}")

    def wait_and_retry(self, max_retries=3, base_wait=30):
        """等待并重试机制"""
        for attempt in range(max_retries):
            try:
                is_blocked, reason = self.detect_anti_bot()
                if not is_blocked:
                    return True
            except:
                pass
            
            wait_time = base_wait * (attempt + 1)
            print(f"   Retry {attempt + 1}/{max_retries} after {wait_time}s...")
            time.sleep(wait_time)
            
            try:
                if self.page and not self.page.is_closed():
                    self.page.reload(wait_until="networkidle")
                    time.sleep(random.uniform(2, 4))
            except:
                pass
        
        return False

    def generate_username(self, length=12):
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choice(chars) for _ in range(length))

    def generate_email(self, username=None):
        if not username:
            username = self.generate_username()
        return f"{username}@{self.email_domain}"

    def _human_type(self, element, text):
        """模拟人类输入：逐字符输入，带随机延迟"""
        # Playwright 的 ElementHandle 没有 clear() 方法，先清空再输入
        element.fill('')
        for char in text:
            element.type(char, delay=random.randint(50, 150))

    def extract_verification_link(self, content):
        patterns = [
            r'https://github\.com/verify-email[^\s<>"\']+',
            r'https://github\.com/settings/emails/verify[^\s<>"\']+',
            r'https://[^\s<>"\']*github[^\s<>"\']*verify[^\s<>"\']*token=[^\s<>"\']+',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, content)
            if matches:
                return matches[0]
        return None

    def wait_for_email(self, email, timeout=60, max_retries=10):
        print(f"[DEBUG] wait_for_email: Waiting for email to {email}")
        print(f"[DEBUG] wait_for_email: API base: {self.api_base}")
        for i in range(max_retries):
            wait_time = timeout / max_retries
            print(f"[DEBUG] wait_for_email: Attempt {i+1}/{max_retries}, waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
            try:
                url = f"{self.api_base}/to/{email}"
                print(f"[DEBUG] wait_for_email: Checking {url}")
                response = requests.get(url)
                print(f"[DEBUG] wait_for_email: Response status: {response.status_code}")
                emails = json.loads(response.text)
                print(f"[DEBUG] wait_for_email: Found {len(emails)} emails")
                if emails:
                    for email_data in emails:
                        from_addr = email_data.get('from', '').lower()
                        subject = email_data.get('subject', '').lower()
                        print(f"[DEBUG] wait_for_email: Checking email from={from_addr}, subject={subject}")
                        if 'github' in from_addr or 'github' in subject:
                            print("[DEBUG] wait_for_email: Found GitHub email!")
                            link = self.extract_verification_link(email_data.get('content', ''))
                            if link:
                                print(f"[DEBUG] wait_for_email: Extracted link: {link}")
                                return link
                            else:
                                print("[DEBUG] wait_for_email: No verification link found in email")
            except Exception as e:
                print(f"[DEBUG] wait_for_email: Error checking email: {e}")
        print("[DEBUG] wait_for_email: No verification email found after all retries")
        return None

    def register(self, username=None, password=None, email=None):
        if not self.page:
            self.init_driver()

        if not username:
            username = self.generate_username()
        if not email:
            email = self.generate_email(username)
        if not password:
            password = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(16))

        print(f"[DEBUG] Registering: {username} / {email}")

        try:
            print("[DEBUG] Navigating to GitHub signup page...")
            self.page.goto("https://github.com/signup", wait_until="networkidle")
            print(f"[DEBUG] Page loaded. Current URL: {self.page.url}")
            time.sleep(random.uniform(2, 4))
            
            print("[DEBUG] Checking for anti-bot detection...")
            is_blocked, reason = self.detect_anti_bot()
            if is_blocked:
                print(f"[WARN] Anti-bot detected before registration: {reason}")
                print(f"[DEBUG] Page title: {self.page.title()}")
                print(f"[DEBUG] Page URL: {self.page.url}")
                print(f"[INFO] Skipping retry (debug mode)")
                print(f"[DEBUG] Browser window kept open for inspection")
                return {
                    'username': username,
                    'email': email,
                    'status': 'blocked',
                    'reason': reason
                }
            print("[DEBUG] No anti-bot detected, proceeding...")
            
            # 模拟鼠标移动
            try:
                if not self.page.is_closed():
                    print("[DEBUG] Simulating mouse movement...")
                    self.page.mouse.move(random.randint(100, 200), random.randint(100, 200))
                    time.sleep(random.uniform(0.5, 1))
            except Exception as e:
                print(f"[DEBUG] Mouse movement failed: {e}")

            print("[DEBUG] Looking for form inputs...")
            # GitHub 新的注册页面使用不同的选择器
            email_input = self.page.wait_for_selector("#email", timeout=10000)
            print("[DEBUG] Found email input")
            password_input = self.page.wait_for_selector("#password", timeout=10000)
            print("[DEBUG] Found password input")
            username_input = self.page.wait_for_selector("#login", timeout=10000)
            print("[DEBUG] Found username input")

            # 填写表单（按实际页面顺序：Email -> Password -> Username）
            print(f"[DEBUG] Typing email: {email}")
            self._human_type(email_input, email)
            time.sleep(random.uniform(0.8, 1.5))
            
            print("[DEBUG] Typing password...")
            self._human_type(password_input, password)
            time.sleep(random.uniform(0.8, 1.5))
            
            print(f"[DEBUG] Typing username: {username}")
            self._human_type(username_input, username)
            time.sleep(random.uniform(1, 3))

            # 查找提交按钮 - 应该点击可见的 type="button" 按钮，而不是隐藏的 submit 按钮
            print("[DEBUG] Looking for submit button...")
            submit_button = None
            
            # 首先尝试找到可见的 "Create account" 按钮（type="button"）
            # 这个按钮会触发验证码加载，然后显示真正的 submit 按钮
            try:
                buttons = self.page.query_selector_all('button')
                for btn in buttons:
                    button_text = btn.inner_text().strip()
                    if "Create account" in button_text:
                        # 检查按钮是否可见
                        is_visible = btn.evaluate('el => el.offsetParent !== null')
                        if is_visible:
                            submit_button = btn
                            print(f"[DEBUG] Found visible Create account button: type={btn.evaluate('el => el.type')}")
                            break
            except Exception as e:
                print(f"[DEBUG] Error finding button: {e}")
            
            if submit_button:
                print("[DEBUG] Found submit button, clicking...")
                time.sleep(random.uniform(0.3, 0.8))
                submit_button.click()
                time.sleep(random.uniform(0.3, 0.8))
                submit_button.click()
                print("[DEBUG] Submit button clicked")


                time.sleep(random.uniform(60, 80))
                
                # 等待验证码加载或真正的 submit 按钮出现
                print("[DEBUG] Waiting for form submission or CAPTCHA...")
                time.sleep(random.uniform(2, 3))
                
                # 检查是否有真正的 submit 按钮出现（验证码加载后）
                try:
                    real_submit = self.page.query_selector('button.js-octocaptcha-form-submit[type="submit"]')
                    if real_submit:
                        is_visible = real_submit.evaluate('el => el.offsetParent !== null && window.getComputedStyle(el).display !== "none"')
                        if is_visible:
                            print("[DEBUG] Found real submit button after CAPTCHA, clicking...")
                            real_submit.click()
                            time.sleep(1)
                except:
                    pass
            else:
                print("[WARN] Submit button not found!")

            time.sleep(random.uniform(2, 4))
            print(f"[DEBUG] After submit. Current URL: {self.page.url}")
            
            print("[DEBUG] Checking for anti-bot after submission...")
            is_blocked, reason = self.detect_anti_bot()
            if is_blocked:
                print(f"[WARN] Anti-bot detected after submission: {reason}")
                print(f"[DEBUG] Page title: {self.page.title()}")
                print(f"[DEBUG] Page URL: {self.page.url}")
                print(f"[INFO] Skipping retry (debug mode)")
                print(f"[DEBUG] Browser window kept open for inspection")
                return {
                    'username': username,
                    'email': email,
                    'status': 'blocked',
                    'reason': reason
                }
            print("[DEBUG] No anti-bot detected after submission")

            # 等待页面跳转或显示验证信息
            print("[DEBUG] Waiting for page response after submission...")
            time.sleep(random.uniform(2, 4))
            
            # 检查是否需要点击验证按钮（新页面可能不需要）
            print("[DEBUG] Checking for email verification step...")
            try:
                # 尝试多种可能的验证按钮选择器
                verify_selectors = [
                    "button[data-continue-to='email-verification']",
                    "button:has-text('Verify')",
                    "button:has-text('Continue')",
                    "a[href*='verify']"
                ]
                
                verify_button = None
                for selector in verify_selectors:
                    try:
                        verify_button = self.page.query_selector(selector)
                        if verify_button:
                            print(f"[DEBUG] Found verification button with selector: {selector}")
                            verify_button.click()
                            time.sleep(2)
                            print("[DEBUG] Verification button clicked")
                            break
                    except:
                        continue
                
                if not verify_button:
                    print("[DEBUG] No verification button found, may have auto-proceeded")
            except Exception as e:
                print(f"[DEBUG] Verification button check failed: {e}")

            print("[DEBUG] Registration request sent, waiting for verification email...")
            verification_link = self.wait_for_email(email)
            
            if verification_link:
                print(f"[DEBUG] Found verification link: {verification_link}")
                print("[DEBUG] Navigating to verification link...")
                self.page.goto(verification_link, wait_until="networkidle")
                print(f"[DEBUG] After verification. Current URL: {self.page.url}")
                time.sleep(3)
                
                if "github.com" in self.page.url and "verify" not in self.page.url:
                    print(f"[OK] Account verified: {username} / {email}")
                    
                    print("[SIM] Simulating normal user behavior...")
                    self.simulate_normal_behavior(username, self.target_repo)
                    
                    return {
                        'username': username,
                        'email': email,
                        'password': password,
                        'status': 'success'
                    }
                else:
                    print(f"[FAIL] Verification may have failed: {username}")
                    print(f"[DEBUG] Final URL: {self.page.url}")
            else:
                print(f"[FAIL] No verification email received: {username}")

        except Exception as e:
            print(f"[FAIL] Error: {e}")
            import traceback
            print(f"[DEBUG] Traceback:\n{traceback.format_exc()}")

        return {
            'username': username,
            'email': email,
            'status': 'failed'
        }

    def simulate_normal_behavior(self, username, target_repo="sribdcn/PersonalExam"):
        """模拟正常用户行为"""
        try:
            print("  -> Visiting profile page...")
            self.page.goto(f"https://github.com/{username}", wait_until="networkidle")
            time.sleep(random.uniform(2, 4))
            
            popular_repos = [
                "microsoft/vscode", "facebook/react", "vuejs/vue",
                "tensorflow/tensorflow", "pytorch/pytorch", "microsoft/TypeScript"
            ]
            
            repos_to_visit = random.sample(popular_repos, random.randint(2, 3))
            for repo in repos_to_visit:
                print(f"  -> Browsing repository: {repo}...")
                self.page.goto(f"https://github.com/{repo}", wait_until="networkidle")
                time.sleep(random.uniform(3, 6))
                self._simulate_scrolling()
                time.sleep(random.uniform(2, 4))
            
            print("  -> Exploring GitHub...")
            self.page.goto("https://github.com/explore", wait_until="networkidle")
            time.sleep(random.uniform(2, 4))
            self._simulate_scrolling()
            time.sleep(random.uniform(2, 3))
            
            print(f"  -> Discovering repository: {target_repo}...")
            self.page.goto(f"https://github.com/{target_repo}", wait_until="networkidle")
            time.sleep(random.uniform(3, 5))
            self._simulate_scrolling()
            time.sleep(random.uniform(2, 3))
            
            try:
                readme_section = self.page.query_selector("div[data-testid='readme']")
                if readme_section:
                    print("  -> Reading README...")
                    readme_section.scroll_into_view_if_needed()
                    time.sleep(random.uniform(3, 5))
                    self._simulate_scrolling()
                    time.sleep(random.uniform(2, 3))
            except:
                pass
            
            try:
                print(f"  -> Starring repository: {target_repo}...")
                star_selectors = [
                    "button[data-hydro-click*='star']",
                    "form[action*='star'] button",
                    "button[aria-label*='Star']",
                    "button[title*='Star']",
                ]
                
                star_button = None
                for selector in star_selectors:
                    elements = self.page.query_selector_all(selector)
                    for elem in elements:
                        text = elem.inner_text().strip().lower()
                        if "star" in text and "unstar" not in text:
                            star_button = elem
                            break
                    if star_button:
                        break
                
                if star_button:
                    button_text = star_button.inner_text().strip().lower()
                    if "star" in button_text and "unstar" not in button_text:
                        star_button.hover()
                        time.sleep(random.uniform(0.5, 1))
                        star_button.click()
                        time.sleep(random.uniform(1, 2))
                        print(f"    [OK] Successfully starred {target_repo}")
                    else:
                        print(f"    [INFO] Already starred")
                else:
                    print(f"    [WARN] Could not find star button")
            except Exception as e:
                print(f"    [WARN] Could not star repository: {e}")
            
            print("  -> Returning to profile...")
            self.page.goto(f"https://github.com/{username}", wait_until="networkidle")
            time.sleep(random.uniform(2, 3))
            
            print("  [OK] Normal user behavior simulation completed")
            
        except Exception as e:
            print(f"  [WARN] Error during behavior simulation: {e}")

    def _simulate_scrolling(self):
        """模拟人类滚动行为"""
        try:
            scroll_count = random.randint(2, 4)
            for _ in range(scroll_count):
                scroll_amount = random.randint(300, 800)
                self.page.evaluate(f"window.scrollBy(0, {scroll_amount});")
                time.sleep(random.uniform(0.5, 1.5))
            
            if random.random() > 0.7:
                self.page.evaluate("window.scrollTo(0, 0);")
                time.sleep(random.uniform(0.5, 1))
        except:
            pass

    def batch_register(self, count=10):
        results = []
        try:
            for i in range(count):
                result = self.register()
                results.append(result)
                
                if result.get('status') == 'blocked':
                    wait_time = random.uniform(60, 120)
                    print(f"[WARN] Blocked detected, waiting {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    
                    if self.blocked_count >= 3:
                        print("[WARN] Too many blocks, consider changing IP or waiting longer")
                        if self.proxy_list:
                            self.rotate_proxy()
                            self.close_driver()
                            time.sleep(5)
                            self.init_driver()
                        else:
                            print("[WARN] No proxy available, stopping batch registration")
                            break
                
                if i < count - 1:
                    base_delay = 30 if result.get('status') == 'blocked' else 15
                    delay = random.uniform(base_delay, base_delay + 10)
                    print(f"Waiting {delay:.1f}s before next registration...")
                    time.sleep(delay)
        finally:
            self.close_driver()
        return results


if __name__ == "__main__":
    import sys
    
    email_domain = sys.argv[1] if len(sys.argv) > 1 else "sayhiai.com"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    headless = sys.argv[3].lower() == "headless" if len(sys.argv) > 3 else False
    proxy = sys.argv[4] if len(sys.argv) > 4 else None
    
    proxy_list = None
    if proxy and ',' in proxy:
        proxy_list = [p.strip() for p in proxy.split(',')]
        proxy = proxy_list[0]
    
    register = GitHubRegister(email_domain, headless=headless, proxy=proxy, proxy_list=proxy_list)
    
    try:
        if count == 1:
            result = register.register()
            if result.get('status') == 'blocked':
                print("\n[DEBUG] Browser kept open for debugging. Press Enter to close...")
                input()
        else:
            results = register.batch_register(count)
            success = sum(1 for r in results if r['status'] == 'success')
            print(f"\nCompleted: {success}/{count} successful")
    finally:
        register.close_driver()
