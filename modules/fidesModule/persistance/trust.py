from typing import List, Optional, Union

from redis.client import Redis
from tensorflow.python.ops.numpy_ops.np_utils import result_type_unary

from ..messaging.model import PeerInfo
from ..model.aliases import PeerId, Target, OrganisationId
from ..model.configuration import TrustModelConfiguration
from ..model.peer_trust_data import PeerTrustData, TrustMatrix
from ..model.threat_intelligence import SlipsThreatIntelligence
from ..persistence.trust import TrustDatabase

from slips_files.core.database.database_manager import DBManager
import json
from ..utils.time import Time, now

# because this will be implemented
# noinspection DuplicatedCode
class SlipsTrustDatabase(TrustDatabase):
    """Trust database implementation that uses Slips redis as a storage."""

    # TODO: [S] implement this

    def __init__(self, configuration: TrustModelConfiguration, db : DBManager):
        super().__init__(configuration)
        self.db = db

    def store_connected_peers_list(self, current_peers: List[PeerInfo]):
        """Stores list of peers that are directly connected to the Slips."""

        json_peers = [json.dumps(peer.to_dict()) for peer in current_peers]
        self.db.store_connected_peers(json_peers)

    def get_connected_peers(self) -> List[PeerInfo]:
        """Returns list of peers that are directly connected to the Slips."""
        json_peers = self.db.get_connected_peers()
        current_peers = [PeerInfo(**json.loads(peer_json)) for peer_json in json_peers]
        return current_peers

    def get_peers_with_organisations(self, organisations: List[OrganisationId]) -> List[PeerInfo]:
        """Returns list of peers that have one of given organisations."""
        raise NotImplemented()

    def get_peers_with_geq_recommendation_trust(self, minimal_recommendation_trust: float) -> List[PeerInfo]:
        """Returns peers that have >= recommendation_trust then the minimal."""
        connected_peers = self.get_connected_peers()
        out = []
        for peer in connected_peers:
            td = self.get_peer_trust_data(peer.id)

            if td is not None and td.recommendation_trust >= minimal_recommendation_trust:
                out.append(peer)
        return out


    def store_peer_trust_data(self, trust_data: PeerTrustData):
        """Stores trust data for given peer - overwrites any data if existed."""
        id = trust_data.id
        td_json = json.dumps(trust_data.to_dict())
        self.db.store_peer_trust_data(id, td_json)

    def store_peer_trust_matrix(self, trust_matrix: TrustMatrix):
        """Stores trust matrix."""
        for peer in trust_matrix.values():
            self.store_peer_trust_data(peer)

    def get_peer_trust_data(self, peer: Union[PeerId, PeerInfo]) -> Optional[PeerTrustData]:
        """Returns trust data for given peer ID, if no data are found, returns None."""
        if isinstance(peer, PeerId):
            peer_id = peer
        elif isinstance(peer, PeerInfo):
            peer_id = peer.id
        else:
            return None

        td_json = self.db.get_peer_trust_data(peer.id)
        if td_json is None:
            return None
        return PeerTrustData(**json.loads(td_json))


    def get_peers_trust_data(self, peer_ids: List[Union[PeerId, PeerInfo]]) -> TrustMatrix:
        """Return trust data for each peer from peer_ids."""
        return {peer_id: self.get_peer_trust_data(peer_id) for peer_id in peer_ids}

    def cache_network_opinion(self, ti: SlipsThreatIntelligence):
        """Caches aggregated opinion on given target."""
        self.db.cache_network_opinion(ti.target, ti.to_dict())

    def get_cached_network_opinion(self, target: Target) -> Optional[SlipsThreatIntelligence]:
        """Returns cached network opinion. Checks cache time and returns None if data expired."""
        rec = self.db.get_cached_network_opinion(target, self.__configuration.network_opinion_cache_valid_seconds, now())
        if rec is None:
            return None
        else:
            return SlipsThreatIntelligence.from_dict(rec)

