using System.Text.Json;
using SteamDepotDumper.Services;
using SteamKit2;

namespace SteamDepotDumper;

class Program
{
    static async Task Main(string[] args)
    {
        if (args.Length < 1)
        {
            Console.WriteLine("Usage: dotnet run -- <app-id> [--guard-file <path>] [--output <path>]");
            return;
        }

        if (!uint.TryParse(args[0], out uint appId))
        {
            Console.WriteLine("Invalid App ID.");
            return;
        }

        string sessionFile = "guard.json";
        string? outputFile = null;

        for (int i = 1; i < args.Length; i++)
        {
            if (args[i] == "--guard-file" && i + 1 < args.Length)
            {
                sessionFile = args[++i];
            }
            else if (args[i] == "--output" && i + 1 < args.Length)
            {
                outputFile = args[++i];
            }
        }

        try
        {
            var auth = new SteamAuth(sessionFile);
            
            // Try to log in with existing session first
            var sessionResult = await auth.LogOnWithSessionAsync();
            SteamClient client;
            CallbackManager manager;

            if (sessionResult != null)
            {
                client = sessionResult.Value.Client;
                manager = sessionResult.Value.Manager;
            }
            else
            {
                // Fallback to credentials
                Console.WriteLine("No valid session found or session expired. Please log in.");
                Console.Write("Username: ");
                string? username = Console.ReadLine();
                if (string.IsNullOrEmpty(username)) return;

                Console.Write("Password: ");
                string password = ReadPassword();
                if (string.IsNullOrEmpty(password)) return;

                var credentialsResult = await auth.LogOnWithCredentialsAsync(username, password);
                client = credentialsResult.Client;
                manager = credentialsResult.Manager;
            }

            var fetcher = new AppInfoFetcher(client);
            var result = await fetcher.FetchAppInfoAsync(appId);

            var jsonOptions = new JsonSerializerOptions { WriteIndented = true };
            string jsonOutput = JsonSerializer.Serialize(result, jsonOptions);

            if (outputFile != null)
            {
                await File.WriteAllTextAsync(outputFile, jsonOutput);
                Console.WriteLine($"\nOutput saved to {outputFile}");
            }
            else
            {
                Console.WriteLine("\n--- JSON OUTPUT ---");
                Console.WriteLine(jsonOutput);
            }

            // Disconnect gracefully
            client.Disconnect();
        }
        catch (Exception ex)
        {
            Console.WriteLine($"\nError: {ex.Message}");
        }
    }

    static string ReadPassword()
    {
        string password = "";
        while (true)
        {
            var key = Console.ReadKey(true);
            if (key.Key == ConsoleKey.Enter) break;
            if (key.Key == ConsoleKey.Backspace && password.Length > 0)
            {
                password = password[..^1];
            }
            else if (!char.IsControl(key.KeyChar))
            {
                password += key.KeyChar;
            }
        }
        Console.WriteLine();
        return password;
    }
}
