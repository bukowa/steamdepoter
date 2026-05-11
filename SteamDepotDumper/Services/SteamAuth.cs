using SteamKit2;
using SteamKit2.Authentication;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace SteamDepotDumper.Services;

public class SessionData
{
    public string? AccountName { get; set; }
    public string? RefreshToken { get; set; }
    public string? GuardData { get; set; }
}

public class SteamAuth
{
    private readonly string _sessionFilePath;
    private readonly SteamClient _steamClient;
    private readonly CallbackManager _manager;
    private readonly SteamUser _steamUser;
    private SessionData? _session;

    public SteamAuth(string sessionFilePath)
    {
        _sessionFilePath = sessionFilePath;
        _steamClient = new SteamClient();
        _manager = new CallbackManager(_steamClient);
        _steamUser = _steamClient.GetHandler<SteamUser>() 
                     ?? throw new Exception("Could not get SteamUser handler.");
        _session = LoadSession();
    }

    public async Task<(SteamClient Client, CallbackManager Manager)?> LogOnWithSessionAsync()
    {
        if (_session?.RefreshToken == null || _session?.AccountName == null)
            return null;

        Console.WriteLine($"Attempting login with saved session for {_session.AccountName}...");
        
        var tcs = new TaskCompletionSource<bool>();

        _manager.Subscribe<SteamClient.ConnectedCallback>(callback =>
        {
            _steamUser.LogOn(new SteamUser.LogOnDetails
            {
                Username = _session.AccountName,
                AccessToken = _session.RefreshToken,
                ShouldRememberPassword = true,
            });
        });

        _manager.Subscribe<SteamClient.DisconnectedCallback>(callback =>
        {
            tcs.TrySetResult(false);
        });

        _manager.Subscribe<SteamUser.LoggedOnCallback>(callback =>
        {
            if (callback.Result == EResult.OK)
            {
                Console.WriteLine("Successfully logged on using saved session!");
                tcs.TrySetResult(true);
            }
            else
            {
                Console.WriteLine($"Saved session login failed: {callback.Result}");
                tcs.TrySetResult(false);
            }
        });

        _steamClient.Connect();

        using var cts = new CancellationTokenSource();
        _ = Task.Run(() =>
        {
            while (!cts.IsCancellationRequested)
            {
                _manager.RunWaitCallbacks(TimeSpan.FromMilliseconds(100));
            }
        });

        var success = await tcs.Task;
        cts.Cancel();

        if (success)
            return (_steamClient, _manager);

        _steamClient.Disconnect();
        return null;
    }

    public async Task<(SteamClient Client, CallbackManager Manager)> LogOnWithCredentialsAsync(string username, string password)
    {
        var tcs = new TaskCompletionSource<bool>();
        bool connected = false;

        _manager.Subscribe<SteamClient.ConnectedCallback>(async callback =>
        {
            connected = true;
            Console.WriteLine("Connected to Steam! Starting authentication...");

            var authSession = await _steamClient.Authentication.BeginAuthSessionViaCredentialsAsync(new AuthSessionDetails
            {
                Username = username,
                Password = password,
                IsPersistentSession = true,
                GuardData = _session?.GuardData,
                Authenticator = new UserConsoleAuthenticator(),
            });

            var pollResponse = await authSession.PollingWaitForResultAsync();

            _session ??= new SessionData();
            _session.AccountName = pollResponse.AccountName;
            _session.RefreshToken = pollResponse.RefreshToken;
            if (pollResponse.NewGuardData != null)
            {
                _session.GuardData = pollResponse.NewGuardData;
            }
            SaveSession(_session);

            _steamUser.LogOn(new SteamUser.LogOnDetails
            {
                Username = pollResponse.AccountName,
                AccessToken = pollResponse.RefreshToken,
                ShouldRememberPassword = true,
            });
        });

        _manager.Subscribe<SteamClient.DisconnectedCallback>(callback =>
        {
            if (!connected)
            {
                Console.WriteLine("Unable to connect to Steam.");
                tcs.TrySetResult(false);
            }
        });

        _manager.Subscribe<SteamUser.LoggedOnCallback>(callback =>
        {
            if (callback.Result != EResult.OK)
            {
                Console.WriteLine($"Login failed: {callback.Result}");
                tcs.TrySetResult(false);
                return;
            }

            Console.WriteLine("Successfully logged on!");
            tcs.TrySetResult(true);
        });

        _steamClient.Connect();

        using var cts = new CancellationTokenSource();
        _ = Task.Run(() =>
        {
            while (!cts.IsCancellationRequested)
            {
                _manager.RunWaitCallbacks(TimeSpan.FromMilliseconds(100));
            }
        });

        var success = await tcs.Task;
        cts.Cancel();

        if (!success)
        {
            throw new Exception("Authentication failed.");
        }

        return (_steamClient, _manager);
    }

    private SessionData? LoadSession()
    {
        if (File.Exists(_sessionFilePath))
        {
            try
            {
                string json = File.ReadAllText(_sessionFilePath);
                if (!json.Trim().StartsWith("{"))
                {
                    return new SessionData { GuardData = json.Trim() };
                }
                return JsonSerializer.Deserialize<SessionData>(json);
            }
            catch { }
        }
        return null;
    }

    private void SaveSession(SessionData session)
    {
        try
        {
            string json = JsonSerializer.Serialize(session, new JsonSerializerOptions { WriteIndented = true });
            File.WriteAllText(_sessionFilePath, json);
            Console.WriteLine($"Session data saved to {_sessionFilePath}");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Warning: Could not save session data: {ex.Message}");
        }
    }
}
