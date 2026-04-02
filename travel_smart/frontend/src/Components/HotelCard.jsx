import React from 'react'
import { Link } from 'react-router-dom'
import { assets } from '../assets/assets'

const HotelCard = ({room, index}) => {
  return (
    <Link to={`./rooms/` + room.id} onClick={() => scrollTo(0,0)} key={room.id}>
        <img src={room.images[0]} alt="" />
        <p>Best Seller</p>
        <div>
            <div>
                <p>{room.hotel.name}</p>
                <div>
                    <img src={assets.starIconFilled} alt="" />
                </div>
            </div>
        </div>
    </Link>
  )
}

export default HotelCard