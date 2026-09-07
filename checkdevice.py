import win32com.client

for device in win32com.client.GetObject("winmgmts:").InstancesOf("Win32_PnPEntity"):
    print(device.Name)
