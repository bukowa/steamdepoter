using System.Text.Json.Serialization;

namespace SteamDepotDumper.Models;

public class AppDump
{
    [JsonPropertyName("app_id")]
    public uint AppId { get; set; }

    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("depots")]
    public List<DepotDump> Depots { get; set; } = new();
}

public class DepotDump
{
    [JsonPropertyName("depot_id")]
    public uint DepotId { get; set; }

    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("max_size")]
    public ulong MaxSize { get; set; }

    [JsonPropertyName("manifests")]
    public List<ManifestInfo> Manifests { get; set; } = new();
}

public class ManifestInfo
{
    [JsonPropertyName("manifest_id")]
    public ulong ManifestId { get; set; }

    [JsonPropertyName("branch")]
    public string Branch { get; set; } = string.Empty;
}
