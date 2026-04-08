import React from 'react'
import { roomsDummyData } from '../assets/assets'
import HotelCard from './HotelCard'
import Title from './Title'
import { useNavigate } from 'react-router-dom'

const FeaturedDestination = () => {
    const naviagte = useNavigate();

    return (
        <div className='flex flex-col items-center px-6 md:px-16 lg:px-24 bg-slate-50 py-20'>
            <Title title='Featured Destination' subtitle='Discover our handpicked selection of exceptional properties around the world, offering unparalleled luxury and unforgettable experiences.' />
            <div className='grid grid-cols-1 md:grid-cols-4 gap-8 mt-20'>
                {roomsDummyData.slice(0, 8).map((room, index) => (
                    <HotelCard key={room.id} room={room} index={index} />
                ))}
            </div>
            <button onClick={() => { naviagte('./rooms'); scrollTo(0, 0) }}
                className='mt-20 rounded bg-white border py-2 px-4 cursor-pointer'>
                View All Destinations
            </button>
        </div>
    )
}

export default FeaturedDestination