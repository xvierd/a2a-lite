import com.a2alite.AgentNetwork;
import com.a2alite.errors.RemoteAgentException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executors;

// Single-source launcher using the Lite fixture's compiled classpath.
class ReverseClient {
    public static void main(String[] args) throws Exception {
        var url = args[0];
        var network = new AgentNetwork();
        for (String tenant : List.of("blue", "green")) {
            network.add(tenant, url + "/" + tenant);
            var endpoint = network.discoverNamed(tenant).getUrl();
            if (!endpoint.equals(url + "/rpc")) throw new AssertionError("Selected interface " + endpoint);
        }
        var pool = Executors.newFixedThreadPool(2);
        try {
            var blue = pool.submit(() -> network.call("blue", "tenant", Map.of(), 10));
            var green = pool.submit(() -> network.call("green", "tenant", Map.of(), 10));
            if (!"blue".equals(blue.get()) || !"green".equals(green.get())) {
                throw new AssertionError("Expected blue and green, received " + blue.get() + " and " + green.get());
            }
        } finally {
            pool.shutdownNow();
        }

        var chunks = new ArrayList<>();
        try (var stream = network.stream("blue", "streamError", Map.of(), 10)) {
            stream.forEach(chunks::add);
            throw new AssertionError("streamError ended without the remote error");
        } catch (RemoteAgentException exc) {
            if (!Integer.valueOf(-32602).equals(exc.getCode())) throw exc;
        }
        if (!chunks.equals(List.of("before-error:blue"))) throw new AssertionError("Chunks before error: " + chunks);
        System.out.println("A2A_LITE_STREAM_ERROR_VERIFIED");
    }
}
