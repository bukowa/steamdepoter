using SteamKit2;
using SteamDepotDumper.Models;
using System.Collections.Concurrent;

namespace SteamDepotDumper.Services;

public class AppInfoFetcher
{
    private readonly SteamClient _steamClient;
    private readonly SteamApps _steamApps;

    public AppInfoFetcher(SteamClient steamClient)
    {
        _steamClient = steamClient;
        _steamApps = _steamClient.GetHandler<SteamApps>() 
                     ?? throw new Exception("Could not get SteamApps handler.");
    }

    public async Task<AppDump> FetchAppInfoAsync(uint appId)
    {
        Console.WriteLine($"Fetching access tokens for App {appId}...");
        var initialTokens = await _steamApps.PICSGetAccessTokens(appId, package: null);
        initialTokens.AppTokens.TryGetValue(appId, out ulong appAccessToken);

        Console.WriteLine($"Fetching product info for App {appId}...");
        var appRequest = new SteamApps.PICSRequest(appId, appAccessToken);
        var appResultSet = await _steamApps.PICSGetProductInfo(app: appRequest, package: null, metaDataOnly: false);

        if (!appResultSet.Complete || appResultSet.Results == null || !appResultSet.Results.Any())
        {
            throw new Exception("Failed to retrieve app product info.");
        }

        var appProductInfo = appResultSet.Results.First();
        var appKv = appProductInfo.Apps[appId].KeyValues;

        var dump = new AppDump
        {
            AppId = appId,
            Name = appKv["common"]["name"].AsString() ?? "Unknown"
        };

        // Gather all depot IDs from the app info
        var depotIds = new HashSet<uint>();
        var depotsNode = appKv["depots"];
        foreach (var depotKv in depotsNode.Children)
        {
            if (uint.TryParse(depotKv.Name, out uint depotId))
            {
                depotIds.Add(depotId);
            }
        }

        Console.WriteLine($"Found {depotIds.Count} depots. Fetching deep metadata for shared/linked depots...");

        // Fetch tokens for all depots individually
        var depotTokens = new ConcurrentDictionary<uint, ulong>();
        var tokenTasks = depotIds.Select(async id =>
        {
            try
            {
                var result = await _steamApps.PICSGetAccessTokens(id, package: null);
                if (result.AppTokens.TryGetValue(id, out ulong token))
                {
                    depotTokens[id] = token;
                }
            }
            catch { }
        });
        await Task.WhenAll(tokenTasks);
        
        // Fetch product info for all depots in bulk
        var depotRequests = depotIds.Select(id => {
            depotTokens.TryGetValue(id, out ulong token);
            return new SteamApps.PICSRequest(id, token);
        }).ToList();

        // Fix: Pass an empty list for packages instead of null
        var emptyPackages = new List<SteamApps.PICSRequest>();
        var depotResultSet = await _steamApps.PICSGetProductInfo(apps: depotRequests, packages: emptyPackages, metaDataOnly: false);
        
        var depotMetadataMap = new Dictionary<uint, KeyValue>();
        if (depotResultSet.Results != null)
        {
            foreach (var result in depotResultSet.Results)
            {
                foreach (var kvPair in result.Apps)
                {
                    depotMetadataMap[kvPair.Key] = kvPair.Value.KeyValues;
                }
            }
        }

        // Now build the final dump by merging App info and Depot info
        foreach (var depotId in depotIds)
        {
            var appDepotKv = depotsNode[depotId.ToString()];
            var deepDepotKv = depotMetadataMap.GetValueOrDefault(depotId);

            var depotDump = new DepotDump
            {
                DepotId = depotId,
                Name = deepDepotKv?["common"]["name"].AsString() 
                       ?? appDepotKv["name"].AsString() 
                       ?? "Unknown",
                
                MaxSize = deepDepotKv?["maxsize"].AsUnsignedLong() 
                          ?? appDepotKv["maxsize"].AsUnsignedLong()
            };

            var manifests = new Dictionary<string, ulong>();
            ProcessManifestNode(appDepotKv["manifests"], manifests);
            ProcessManifestNode(appDepotKv["encrypted_manifests"], manifests);

            if (deepDepotKv != null)
            {
                ProcessManifestNode(deepDepotKv["manifests"], manifests);
                ProcessManifestNode(deepDepotKv["encrypted_manifests"], manifests);
                ProcessManifestNode(deepDepotKv["depots"][depotId.ToString()]["manifests"], manifests);
            }

            foreach (var m in manifests)
            {
                depotDump.Manifests.Add(new ManifestInfo
                {
                    Branch = m.Key,
                    ManifestId = m.Value
                });
            }

            dump.Depots.Add(depotDump);
        }

        return dump;
    }

    private void ProcessManifestNode(KeyValue node, Dictionary<string, ulong> result)
    {
        if (node == null || node == KeyValue.Invalid) return;

        foreach (var branchKv in node.Children)
        {
            string branchName = branchKv.Name ?? "unknown";
            ulong manifestId = 0;

            if (!string.IsNullOrEmpty(branchKv.Value))
            {
                ulong.TryParse(branchKv.Value, out manifestId);
            }
            else if (branchKv["gid"] != KeyValue.Invalid && !string.IsNullOrEmpty(branchKv["gid"].Value))
            {
                ulong.TryParse(branchKv["gid"].Value, out manifestId);
            }

            if (manifestId != 0)
            {
                result[branchName] = manifestId;
            }
        }
    }
}
