import smtplib  
from email.mime.text import MIMEText  
from email.header import Header  
from email.utils import formataddr  
  
# SMTP服务器和端口  
smtp_server = 'smtp.qiye.aliyun.com'  
smtp_port = 465  # 注意：对于QQ邮箱，可能需要使用SSL加密的465端口或TLS加密的587端口  
  
# 发件人和收件人信息  
sender = 'z.f.zhang@i4ai.org'  # 你的邮箱地址  
password = 'Woshishabi1'    # 你的邮箱密码或授权码  
receivers = ['y.t.sun@i4ai.org']  # 收件人邮箱列表  
  
# 邮件内容  
msg = MIMEText('这是邮件的正文内容，纯文本格式。', 'plain', 'utf-8')  
msg['From'] = formataddr((str(Header("发件人姓名", 'utf-8')), sender))  
msg['To'] = ", ".join(
    formataddr((str(Header("收件人姓名", 'utf-8')), receiver)) for receiver in receivers
)  
msg['Subject'] = Header('邮件主题', 'utf-8')  
  
try:  
    # 连接到SMTP服务器  
    # server = smtplib.SMTP(smtp_server, smtp_port)  
    # 如果需要SSL加密，则使用SMTP_SSL类并指定端口为465  
    server = smtplib.SMTP_SSL(smtp_server, 465)  
      
    # 登录SMTP服务器  
    server.login(sender, password)  
      
    # 发送邮件  
    server.sendmail(sender, receivers, msg.as_string())  
      
    # 关闭连接  
    server.quit()  
    print("邮件发送成功！")  
except smtplib.SMTPException as e:  
    print("邮件发送失败：", e)