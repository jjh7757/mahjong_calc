// 원본 mahjong-helper 로 mh_risk_cases 장면의 위험도 · 텐파이율 · 합친 위험을 낸다.
// util 패키지 함수(CalculateRiskTiles34, CalcTenpaiRate, CalculateLeftNoSujiTiles, FixWith*, RonPoint*, OutsideTiles, DoraList)는 원본을 그대로 부른다.
// core.go 는 main 패키지라 부를 수 없어서, 사건 처리(core.go:586-695 울기, 772-850 버림) 와 analysisTilesRisk(308-415), doraNum(142-165),
// cli.go mixedRiskTable(161-175) 을 아래에 같은 식으로 옮겼다(줄 단위로 맞춤). firstColumn 정책은 원본에 없는 우리 쪽 확장이라 여기서도 같은 식으로 흉내 낸다.
package main

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/EndlessCheng/mahjong-helper/util"
	"github.com/EndlessCheng/mahjong-helper/util/model"
)

type inMeld struct {
	Seat       int    `json:"seat"`
	Kind       string `json:"kind"`
	Tiles      string `json:"tiles"`
	At         int    `json:"at"`
	UpgradedAt *int   `json:"upgraded_at"`
	Red        bool   `json:"red"`
}

type inCase struct {
	Name     string          `json:"name"`
	Self     int             `json:"self"`
	Dealer   int             `json:"dealer"`
	Round    string          `json:"round_wind"`
	Hand     string          `json:"hand"`
	Dora     string          `json:"dora_indicators"`
	Unknown  string          `json:"unknown_tsumogiri"`
	Discards [][]interface{} `json:"discards"`
	Melds    []inMeld        `json:"melds"`
	Ippatsu  []interface{}   `json:"ippatsu"`
}

type playerInfo struct {
	melds                []*model.Meld
	meldDiscardsAtGlobal []int
	meldDiscardsAt       []int
	isNaki               bool
	discardTiles         []int
	unknown              []bool
	latestDiscardAtGlobal int
	earlyOutsideTiles    []int
	isReached            bool
	canIppatsu           bool
	reachTileAtGlobal    int
	reachTileAt          int
	selfWindTile         int
}

type roundData struct {
	roundWindTile      int
	dealer             int
	doraIndicators     []int
	leftCounts         []int
	globalDiscardTiles []int
	players            []*playerInfo
}

func (p *playerInfo) doraNum(doraList []int) (doraCount int) {
	for _, meld := range p.melds {
		for _, tile := range meld.Tiles {
			for _, doraTile := range doraList {
				if tile == doraTile {
					doraCount++
				}
			}
		}
		if meld.ContainRedFive {
			doraCount++
		}
	}
	return
}

func normalDiscardTiles(discardTiles []int) []int {
	newD := make([]int, len(discardTiles))
	copy(newD, discardTiles)
	for i, discardTile := range newD {
		if discardTile < 0 {
			newD[i] = ^discardTile
		}
	}
	return newD
}

func (d *roundData) descLeftCounts(tile int) {
	d.leftCounts[tile]--
	if d.leftCounts[tile] < 0 {
		panic(fmt.Sprintf("데이터 이상 %d", tile))
	}
}

func tile1(s string) int { return util.MustStrToTiles(s)[0] }

func kindOf(s string) int {
	switch s {
	case "chi":
		return model.MeldTypeChi
	case "pon":
		return model.MeldTypePon
	case "ankan":
		return model.MeldTypeAnkan
	case "minkan":
		return model.MeldTypeMinkan
	case "kakan":
		return model.MeldTypeKakan
	}
	panic(s)
}

// core.go:586-695 (who != 0 와 자가 손패 쪽은 leftCounts 만)
func (d *roundData) open(who int, meld *model.Meld) {
	for _, player := range d.players {
		player.canIppatsu = false
	}
	player := d.players[who]
	if meld.MeldType != model.MeldTypeAnkan {
		player.isNaki = true
	}
	if meld.MeldType == model.MeldTypeKakan {
		if who != 0 {
			d.descLeftCounts(meld.CalledTile)
		} else {
			d.descLeftCounts(meld.CalledTile) // 자가: 뽑을 때 줄었을 패
		}
		for _, _meld := range player.melds {
			if _meld.Tiles[0] == meld.CalledTile {
				_meld.MeldType = model.MeldTypeKakan
				_meld.Tiles = append(_meld.Tiles, meld.CalledTile)
				_meld.ContainRedFive = meld.ContainRedFive
				break
			}
		}
		return
	}
	player.melds = append(player.melds, meld)
	if who != 0 {
		if meld.MeldType != model.MeldTypeAnkan {
			d.leftCounts[meld.CalledTile]++
		}
		for _, tile := range meld.Tiles {
			d.descLeftCounts(tile)
		}
	} else {
		// 자가 울기: 손에서 낸 패는 뽑을 때 이미 줄었다고 친다.
		skipped := meld.MeldType == model.MeldTypeAnkan
		for _, tile := range meld.Tiles {
			if !skipped && tile == meld.CalledTile {
				skipped = true
				continue
			}
			d.descLeftCounts(tile)
		}
	}
}

// core.go:772-850
func (d *roundData) discard(who int, discardTile int, isTsumogiri bool, isReach bool, unknown bool) {
	player := d.players[who]
	if isReach {
		player.isReached = true
		player.canIppatsu = true
	}
	if who == 0 {
		d.descLeftCounts(discardTile) // 뽑을 때 줄었을 패
		d.globalDiscardTiles = append(d.globalDiscardTiles, discardTile)
		player.discardTiles = append(player.discardTiles, discardTile)
		player.unknown = append(player.unknown, false)
		player.latestDiscardAtGlobal = len(d.globalDiscardTiles) - 1
		return
	}
	d.descLeftCounts(discardTile)
	_disTile := discardTile
	if isTsumogiri {
		_disTile = ^_disTile
	}
	d.globalDiscardTiles = append(d.globalDiscardTiles, _disTile)
	player.discardTiles = append(player.discardTiles, _disTile)
	player.unknown = append(player.unknown, unknown)
	player.latestDiscardAtGlobal = len(d.globalDiscardTiles) - 1
	if !player.isReached && len(player.discardTiles) <= 5 {
		player.earlyOutsideTiles = append(player.earlyOutsideTiles, util.OutsideTiles(discardTile)...)
	}
	if player.isReached && player.reachTileAtGlobal == -1 {
		player.reachTileAtGlobal = len(d.globalDiscardTiles) - 1
		player.reachTileAt = len(player.discardTiles) - 1
	} else if len(player.meldDiscardsAt) != len(player.melds) {
		player.meldDiscardsAt = append(player.meldDiscardsAt, len(player.discardTiles)-1)
		player.meldDiscardsAtGlobal = append(player.meldDiscardsAtGlobal, len(d.globalDiscardTiles)-1)
	}
	if player.reachTileAt < len(player.discardTiles)-1 {
		player.canIppatsu = false
	}
}

type riskInfo struct {
	tenpaiRate      float64
	safeTiles34     []bool
	riskTable       []float64
	leftNoSujiTiles []int
	ronPoint        float64
	turns           int
	ippatsu         bool
	riichi          bool
}

// core.go:308-415
func (d *roundData) analysisTilesRisk(firstColumn bool) []*riskInfo {
	riList := make([]*riskInfo, len(d.players))
	for who := range riList {
		riList[who] = &riskInfo{safeTiles34: make([]bool, 34)}
	}
	for who, player := range d.players {
		if who == 0 {
			continue
		}
		for _, tile := range normalDiscardTiles(player.discardTiles) {
			riList[who].safeTiles34[tile] = true
		}
		if player.reachTileAtGlobal != -1 {
			for _, tile := range normalDiscardTiles(d.globalDiscardTiles[player.reachTileAtGlobal:]) {
				riList[who].safeTiles34[tile] = true
			}
		} else if player.latestDiscardAtGlobal != -1 {
			for _, tile := range normalDiscardTiles(d.globalDiscardTiles[player.latestDiscardAtGlobal:]) {
				riList[who].safeTiles34[tile] = true
			}
		}
		for _, meld := range player.melds {
			if meld.IsKan() {
				riList[who].safeTiles34[meld.Tiles[0]] = true
			}
		}
	}
	doraList := model.DoraList(d.doraIndicators, false)
	for who, player := range d.players {
		if who == 0 {
			continue
		}
		turns := util.MinInt(len(player.discardTiles), util.MaxTurns)
		if turns == 0 {
			turns = 1
		}
		if player.isReached {
			riList[who].tenpaiRate = 100.0
		} else {
			discards := player.discardTiles
			if firstColumn && len(player.meldDiscardsAt) > 0 {
				any := false
				for _, u := range player.unknown[player.meldDiscardsAt[len(player.meldDiscardsAt)-1]+1:] {
					any = any || u
				}
				if any {
					discards = make([]int, len(player.discardTiles))
					for i, t := range player.discardTiles {
						if t >= 0 {
							t = ^t
						}
						discards[i] = t
					}
				}
			}
			riList[who].tenpaiRate = util.CalcTenpaiRate(player.melds, discards, player.meldDiscardsAt)
		}
		var ronPoint float64
		switch {
		case player.canIppatsu:
			ronPoint = util.RonPointRiichiIppatsu
		case player.isReached:
			ronPoint = util.RonPointRiichiHiIppatsu
		case player.isNaki:
			ronPoint = util.RonPointOtherNakiWithDora(player.doraNum(doraList))
		default:
			ronPoint = util.RonPointDama
		}
		if who == d.dealer {
			ronPoint *= 1.5
		}
		riList[who].ronPoint = ronPoint
		riList[who].turns = turns
		riList[who].ippatsu = player.canIppatsu
		riList[who].riichi = player.isReached
		risk34 := util.CalculateRiskTiles34(turns, riList[who].safeTiles34, d.leftCounts, doraList, d.roundWindTile, player.selfWindTile).
			FixWithEarlyOutside(player.earlyOutsideTiles).
			FixWithPoint(ronPoint)
		riList[who].riskTable = risk34
		if len(player.melds) < 4 {
			riList[who].leftNoSujiTiles = util.CalculateLeftNoSujiTiles(riList[who].safeTiles34, d.leftCounts)
		} else {
			riList[who].leftNoSujiTiles = []int{}
		}
	}
	return riList
}

// cli.go:161-175
func mixedRiskTable(l []*riskInfo) []float64 {
	mixed := make([]float64, 34)
	for i := range mixed {
		mixedRisk := 0.0
		for _, ri := range l[1:] {
			if ri.tenpaiRate <= 15 {
				continue
			}
			_risk := ri.riskTable[i] * ri.tenpaiRate / 100
			mixedRisk = mixedRisk + _risk - mixedRisk*_risk/100
		}
		mixed[i] = mixedRisk
	}
	return mixed
}

type outSeat struct {
	Tenpai     float64   `json:"tenpai"`
	Turns      int       `json:"turns"`
	RonPoint   float64   `json:"ron_point"`
	Riichi     bool      `json:"riichi"`
	Ippatsu    bool      `json:"ippatsu"`
	Safe       []int     `json:"safe"`
	Risk34     []float64 `json:"risk34"`
	LeftNoSuji []int     `json:"left_no_suji"`
}

type outCase struct {
	Seats  map[string]outSeat `json:"seats"`
	Mixed  []float64          `json:"mixed34"`
	Left34 []int              `json:"left34"`
}

func r6(x float64) float64 {
	return float64(int64(x*1e6+0.5*sign(x))) / 1e6
}

func sign(x float64) float64 {
	if x < 0 {
		return -1
	}
	return 1
}

func run(c inCase) outCase {
	if len(c.Ippatsu) > 0 {
		panic("ippatsu 덮어쓰기는 이 하네스가 다루지 않음")
	}
	rel := func(seat int) int { return ((seat-c.Self)%4 + 4) % 4 }
	dealerRel := rel(c.Dealer)
	d := &roundData{roundWindTile: tile1(c.Round), dealer: dealerRel, leftCounts: util.InitLeftTiles34()}
	for i := 0; i < 4; i++ {
		d.players = append(d.players, &playerInfo{latestDiscardAtGlobal: -1, reachTileAtGlobal: -1, reachTileAt: -1, selfWindTile: 27 + (4-dealerRel+i)%4})
	}
	if c.Dora != "" {
		d.doraIndicators = util.MustStrToTiles(c.Dora)
		for _, t := range d.doraIndicators {
			d.descLeftCounts(t)
		}
	}
	for _, t := range util.MustStrToTiles(c.Hand) {
		d.descLeftCounts(t)
	}
	// 사건 순서: 버림 g 앞에 at == g 인 울기, 가깡은 upgraded_at 에.
	type ev struct {
		pos  int
		meld *inMeld
		up   bool
	}
	evs := map[int][]ev{}
	for i := range c.Melds {
		m := &c.Melds[i]
		evs[m.At] = append(evs[m.At], ev{m.At, m, false})
		if m.UpgradedAt != nil {
			evs[*m.UpgradedAt] = append(evs[*m.UpgradedAt], ev{*m.UpgradedAt, m, true})
		}
	}
	firstCol := c.Unknown == "firstColumn"
	flush := func(g int) {
		for _, e := range evs[g] {
			m := e.meld
			tiles := util.MustStrToTiles(m.Tiles)
			who := rel(m.Seat)
			if e.up {
				d.open(who, &model.Meld{MeldType: model.MeldTypeKakan, Tiles: tiles, CalledTile: tiles[0], ContainRedFive: m.Red})
				continue
			}
			kind := kindOf(m.Kind)
			if kind == model.MeldTypeKakan {
				// 처음엔 퐁(가깡은 upgraded_at 에서). 묶음은 3 장.
				kind = model.MeldTypePon
				tiles = tiles[:3]
			}
			called := tiles[0]
			if kind != model.MeldTypeAnkan {
				var dt string = c.Discards[m.At-1][1].(string)
				called = tile1(dt)
			}
			cp := append([]int(nil), tiles...)
			d.open(who, &model.Meld{MeldType: kind, Tiles: cp, CalledTile: called, ContainRedFive: m.Red})
		}
	}
	for g, dd := range c.Discards {
		flush(g)
		seat := int(dd[0].(float64))
		tile := tile1(dd[1].(string))
		var ts bool
		unknown := dd[2] == nil
		if unknown {
			ts = c.Unknown != "tedashi"
		} else {
			ts = dd[2].(bool)
		}
		d.discard(rel(seat), tile, ts, dd[3].(bool), unknown)
	}
	flush(len(c.Discards))

	ri := d.analysisTilesRisk(firstCol)
	out := outCase{Seats: map[string]outSeat{}, Left34: d.leftCounts}
	for who := 1; who < 4; who++ {
		seat := (c.Self + who) % 4
		r := ri[who]
		risk := make([]float64, 34)
		for i, x := range r.riskTable {
			risk[i] = r6(x)
		}
		safe := []int{}
		for i, s := range r.safeTiles34 {
			if s {
				safe = append(safe, i)
			}
		}
		lns := r.leftNoSujiTiles
		if lns == nil {
			lns = []int{}
		}
		out.Seats[fmt.Sprint(seat)] = outSeat{Tenpai: r6(r.tenpaiRate), Turns: r.turns, RonPoint: r6(r.ronPoint), Riichi: r.riichi, Ippatsu: r.ippatsu, Safe: safe, Risk34: risk, LeftNoSuji: lns}
	}
	mixed := mixedRiskTable(ri)
	for i := range mixed {
		mixed[i] = r6(mixed[i])
	}
	out.Mixed = mixed
	return out
}

func main() {
	raw, err := os.ReadFile(os.Args[1])
	if err != nil {
		panic(err)
	}
	var doc struct {
		Cases []inCase `json:"cases"`
	}
	if err := json.Unmarshal(raw, &doc); err != nil {
		panic(err)
	}
	res := map[string]outCase{}
	for _, c := range doc.Cases {
		res[c.Name] = run(c)
	}
	b, _ := json.MarshalIndent(res, "", " ")
	os.WriteFile(os.Args[2], b, 0644)
	fmt.Println(len(res), "cases")
}
